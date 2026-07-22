"""Entity resolution: match the fund name printed on a notice to a master
entity — deterministically, with calibrated confidence, and with an explicit
refusal to guess.

Matching is exact -> alias -> fuzzy (RapidFuzz token_sort_ratio). No LLM:
resolution must be explainable and reproducible, because a silent mismatch
here corrupts every downstream number (see docs/failure_modes.md).

``resolve`` refuses to auto-select when:
- the top candidate is below the auto-accept threshold,
- the runner-up is within the ambiguity margin (two plausible funds), or
- the notice is addressed to a PARENT fund while allocating across sub-funds
  (money never lands in a parent vehicle — a human picks the sub-fund).

The whole decision path is pure (``score_candidates`` + ``resolve``): the
agent class only adds the database fetch, which is what lets the adversarial
eval suite exercise the real production logic without a database.
"""

from typing import Any

from rapidfuzz import fuzz

from src.agents.base import BaseAgent
from src.config.settings import Settings
from src.core.contracts import EntityCandidate, ResolutionResult
from src.core.state import PolarisState
from src.db.client import audit, db_conn

AMBIGUITY_MARGIN = 0.05

EntityRow = tuple[str, str, str, list[str]]  # (id, name, kind, aliases)


def score_candidates(target: str, entities: list[EntityRow]) -> list[EntityCandidate]:
    target_norm = target.strip().lower()
    out: list[EntityCandidate] = []
    for entity_id, name, kind, aliases in entities:
        if name.strip().lower() == target_norm:
            confidence, method = 0.99, "exact"
        elif any(a.strip().lower() == target_norm for a in aliases):
            confidence, method = 0.95, "alias"
        else:
            ratio = fuzz.token_sort_ratio(target_norm, name.lower()) / 100
            if ratio < 0.55:
                continue
            confidence, method = round(ratio * 0.9, 4), "fuzzy"
        out.append(EntityCandidate(
            entity_id=str(entity_id), name=name, kind=kind,
            confidence=confidence, method=method,
        ))
    return sorted(out, key=lambda c: c.confidence, reverse=True)


def resolve(
    target: str, mentions: list[str], entities: list[EntityRow], settings: Settings
) -> ResolutionResult:
    """The full resolution decision, as a pure function."""
    candidates = score_candidates(target, entities)
    # Sub-funds mentioned in the body are candidates in their own right: for
    # an ambiguous parent-fund notice they are the REAL destinations.
    seen = {c.entity_id for c in candidates}
    for mention in mentions:
        for cand in score_candidates(mention, entities):
            if cand.confidence >= 0.9 and cand.entity_id not in seen:
                candidates.append(cand)
                seen.add(cand.entity_id)
    candidates.sort(key=lambda c: c.confidence, reverse=True)

    if not candidates:
        return ResolutionResult(
            candidates=[], needs_review=True,
            reason="no entity in the master table resembles the notice's fund name",
        )

    top = candidates[0]
    runner_up_gap = (
        top.confidence - candidates[1].confidence if len(candidates) > 1 else 1.0
    )

    if top.kind == "fund" and mentions:
        if any(c.kind == "sub_fund" for c in candidates[1:4]):
            return ResolutionResult(
                candidates=candidates, needs_review=True,
                reason="notice addressed to parent fund but allocates across "
                       "sub-funds — a human must pick the destination vehicle",
            )

    if top.confidence >= settings.entity_match_auto_accept:
        if runner_up_gap < AMBIGUITY_MARGIN:
            return ResolutionResult(
                candidates=candidates, needs_review=True,
                reason=f"two candidates within {AMBIGUITY_MARGIN:.0%} confidence: "
                       f"'{top.name}' vs '{candidates[1].name}'",
            )
        return ResolutionResult(
            candidates=candidates, selected_entity_id=top.entity_id,
            reason=f"'{top.name}' via {top.method} match at {top.confidence:.2f}",
        )

    if top.confidence >= settings.entity_match_review_floor:
        return ResolutionResult(
            candidates=candidates, needs_review=True,
            reason=f"best match '{top.name}' at {top.confidence:.2f} is below "
                   f"auto-accept ({settings.entity_match_auto_accept})",
        )

    return ResolutionResult(
        candidates=candidates, needs_review=True,
        reason=f"no candidate above review floor "
               f"({settings.entity_match_review_floor})",
    )


class EntityResolverAgent(BaseAgent):
    name = "entity_resolver"
    output_key = "resolution"
    output_model = ResolutionResult

    def execute(self, state: PolarisState) -> dict[str, Any]:
        parsed = state["parsed"]
        target = parsed["fund_name_raw"]
        mentions = parsed.get("sub_fund_mentions", [])

        with db_conn() as conn:
            rows = [
                (str(r[0]), r[1], r[2], list(r[3]))
                for r in conn.execute(
                    "select id, name, kind, aliases from entities"
                    " where kind in ('fund', 'sub_fund')"
                ).fetchall()
            ]

        resolution = resolve(target, mentions, rows, self.settings)
        audit(state.get("run_id"), self.name, "entities_resolved", payload={
            "target": target,
            "selected": resolution.selected_entity_id,
            "needs_review": resolution.needs_review,
            "candidates": [(c.name, c.confidence) for c in resolution.candidates[:5]],
        })
        return {
            "resolution": resolution,
            "needs_human": resolution.needs_review,
            "selected_entity_id": resolution.selected_entity_id,
        }
