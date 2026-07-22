"""Adversarial eval runner.

Every case exercises the REAL production functions — resolve(), sanitize(),
grounding_issues(), reconcile_distribution() — against the same entity
universe the seed installs. No mocks, no reimplementation: if a threshold
or regex regresses, these cases fail in CI."""

import json
from pathlib import Path

from src.agents.data_validator import reconcile_distribution
from src.agents.entity_resolver import resolve
from src.config.settings import Settings
from src.db.seed import ENTITIES
from src.guardrails.input_guard import sanitize
from src.guardrails.output_guard import grounding_issues

DATASET = Path(__file__).parent / "datasets" / "adversarial.jsonl"


def load_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def entity_rows() -> list[tuple[str, str, str, list[str]]]:
    return [
        (f"e{i}", name, kind, aliases)
        for i, (name, kind, _parent, aliases, _sector) in enumerate(ENTITIES)
        if kind in ("fund", "sub_fund")
    ]


def run_case(case: dict) -> tuple[bool, str]:
    """Returns (passed, detail-for-humans)."""
    kind = case["kind"]

    if kind == "resolution":
        result = resolve(case["target"], case.get("mentions", []),
                         entity_rows(), Settings(_env_file=None))
        if case["expect"] == "needs_review":
            ok = result.needs_review and result.selected_entity_id is None
            return ok, f"needs_review={result.needs_review}, reason={result.reason!r}"
        selected = next(
            (c.name for c in result.candidates
             if c.entity_id == result.selected_entity_id), None,
        )
        ok = not result.needs_review and selected == case["expect_entity"]
        return ok, f"selected={selected!r}"

    if kind == "injection":
        verdict = sanitize(case["text"])
        missing = [f for f in case["expect_flags"] if f not in verdict.flags]
        leaked = [s for s in case.get("must_not_contain", [])
                  if s.lower() in verdict.sanitized_text.lower()]
        ok = verdict.safe == case["expect_safe"] and not missing and not leaked
        if case["expect_safe"]:
            ok = ok and verdict.flags == []
        return ok, f"flags={verdict.flags}, missing={missing}, leaked={leaked}"

    if kind == "grounding":
        issues = grounding_issues(case["parsed"], case["text"])
        ok = (not issues) == case["expect_grounded"]
        return ok, f"issues={issues}"

    if kind == "reconciliation":
        issues = reconcile_distribution(
            case["amount"], case["prior"], case["feed"],
            [tuple(p) for p in case["peer_moves"]], tolerance=0.10,
        )
        codes = [i.code for i in issues]
        ok = codes == case["expect_codes"]
        if ok and case.get("expect_suspect"):
            suspects = issues[0].details.get("suspects", [])
            ok = any(s["entity"] == case["expect_suspect"] for s in suspects)
        return ok, f"codes={codes}"

    raise ValueError(f"unknown case kind: {kind!r}")
