"""Typed contracts for every agent boundary.

An agent's output is validated against its declared model before it enters
shared state, so a malformed or hallucinated payload is stopped at the
boundary that produced it — not three agents downstream where the blast
radius is a wrong NAV report.
"""

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DocType = Literal["capital_call", "distribution", "quarterly_report"]
Severity = Literal["info", "warning", "critical"]


class GuardVerdict(BaseModel):
    """Input guard's judgement on raw document text, made BEFORE any LLM call."""

    safe: bool
    flags: list[str] = []
    # Text with detected injection spans neutralized; downstream agents only
    # ever see this, never the raw document.
    sanitized_text: str


class ParsedNotice(BaseModel):
    """Structured extraction from a capital call / distribution PDF."""

    doc_type: DocType
    fund_name_raw: str = Field(min_length=2)
    sub_fund_mentions: list[str] = []
    # Bounds are a hallucination tripwire: a $0 or $50T extraction is a
    # contract violation, not a value to propagate.
    amount_usd: float = Field(gt=0, lt=1_000_000_000)
    due_date: date | None = None
    effective_date: date | None = None
    notice_no: str | None = None
    limited_partner: str | None = None
    summary: str = ""


class EntityCandidate(BaseModel):
    entity_id: str
    name: str
    kind: str
    confidence: float = Field(ge=0, le=1)
    method: Literal["exact", "alias", "fuzzy", "embedding"]


class ResolutionResult(BaseModel):
    """Entity resolver output. `selected_entity_id` is only set when the top
    candidate clears the auto-accept threshold with no close runner-up;
    otherwise `needs_review` routes the run to the human gate."""

    candidates: list[EntityCandidate] = []
    selected_entity_id: str | None = None
    needs_review: bool = False
    reason: str = ""


class ValidationIssue(BaseModel):
    code: str  # e.g. "RECON_VARIANCE", "DUPLICATE_NOTICE", "UNKNOWN_ENTITY"
    severity: Severity
    message: str
    details: dict[str, Any] = {}


class ValidationResult(BaseModel):
    issues: list[ValidationIssue] = []
    passed: bool  # False when any critical issue exists


class PositionLine(BaseModel):
    entity_id: str
    name: str
    market_value_usd: float


class PortfolioSnapshot(BaseModel):
    as_of: date
    total_nav_usd: float
    lines: list[PositionLine] = []


class RiskFinding(BaseModel):
    kind: Literal["concentration", "reconciliation_variance", "deadline"]
    severity: Severity
    message: str
    exposure_pct: float | None = None
    entities: list[str] = []


class Report(BaseModel):
    markdown: str = Field(min_length=50)
    citations: list[dict[str, Any]] = []


class AgentError(BaseModel):
    """Structured error record appended to state; the orchestrator routes on
    these instead of letting exceptions unwind the whole graph."""

    agent: str
    error_type: Literal["transient", "permanent", "contract"]
    message: str
    attempts: int = 1
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
