"""Shared LangGraph state.

Everything here must be JSON-serializable: the Postgres checkpointer persists
the full state after every node, which is what makes crash-resume possible.
Agents exchange plain dicts in state; the Pydantic models in contracts.py
validate them at each boundary. `errors` uses an additive reducer so partial
failures accumulate instead of overwriting each other.
"""

import operator
from typing import Annotated, Any, TypedDict


class PolarisState(TypedDict, total=False):
    # identity
    run_id: str
    document_id: str
    storage_path: str

    # ingestion
    raw_text: str
    guard_verdict: dict[str, Any]     # contracts.GuardVerdict
    parsed: dict[str, Any]            # contracts.ParsedNotice

    # enrichment
    resolution: dict[str, Any]        # contracts.ResolutionResult
    validation: dict[str, Any]        # contracts.ValidationResult

    # intelligence
    portfolio: dict[str, Any]         # contracts.PortfolioSnapshot
    risk_findings: list[dict[str, Any]]  # list[contracts.RiskFinding]
    report: dict[str, Any]            # contracts.Report

    # control flow
    needs_human: bool
    human_decision: str | None        # 'approved' | 'rejected'
    selected_entity_id: str | None
    errors: Annotated[list[dict[str, Any]], operator.add]
