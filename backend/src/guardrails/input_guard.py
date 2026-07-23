"""Input guard: sits between PDF text extraction and the first LLM call.

Documents arrive from outside the trust boundary — a malicious counterparty
(or a compromised mailbox) can embed instruction-like text in a notice.
The guard redacts instruction-shaped spans BEFORE any LLM sees the text and
records what it removed; downstream agents only ever receive
``guard_verdict.sanitized_text``. Detection is deterministic regex, not an
LLM: you cannot ask a model to referee text designed to manipulate models.
"""

import re
from typing import Any

from src.agents.base import BaseAgent
from src.core.contracts import GuardVerdict
from src.core.state import AgentState
from src.db.client import audit

MAX_DOC_CHARS = 50_000
REDACTION = "[REDACTED-BY-INPUT-GUARD]"

INJECTION_PATTERNS: dict[str, re.Pattern] = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in {
        "override_instructions": r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions[^.\n]*",
        "system_prompt_spoof": r"system\s+(?:note|prompt|message)\s+to\s+automated[^.\n]*",
        "skip_review": r"skip\s+(?:human\s+)?review[^.\n]*",
        "forced_approval": r"(?:this\s+transaction\s+is\s+)?pre-?approved[^.\n]*",
        "forced_status": r"mark\s+(?:it|this)\s+as\s+(?:confirmed|approved)[^.\n]*",
        "amount_tamper": r"set\s+the\s+amount\s+to[^.\n]*",
        "role_hijack": r"you\s+are\s+now\s+[^.\n]*",
    }.items()
}


def sanitize(raw_text: str) -> GuardVerdict:
    """Pure function: redact instruction-shaped spans, report what was found."""
    flags: list[str] = []
    text = raw_text

    if len(text) > MAX_DOC_CHARS:
        text = text[:MAX_DOC_CHARS]
        flags.append("oversize_truncated")

    for name, pattern in INJECTION_PATTERNS.items():
        text, hits = pattern.subn(REDACTION, text)
        if hits:
            flags.append(f"injection:{name}")

    injection_found = any(f.startswith("injection:") for f in flags)
    return GuardVerdict(safe=not injection_found, flags=flags, sanitized_text=text)


class InputGuardAgent(BaseAgent):
    name = "input_guard"
    output_key = "guard_verdict"
    output_model = GuardVerdict

    def execute(self, state: AgentState) -> dict[str, Any]:
        verdict = sanitize(state["raw_text"])
        audit(state.get("run_id"), self.name, "input_screened",
              level="info" if verdict.safe else "warning",
              payload={"safe": verdict.safe, "flags": verdict.flags})
        return {"guard_verdict": verdict}
