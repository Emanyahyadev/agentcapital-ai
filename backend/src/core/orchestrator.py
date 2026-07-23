"""Orchestration: the LangGraph workflow that coordinates every agent.

Design rules encoded in the graph, not in prose:

- **Validation gates between agents.** An agent's output enters downstream
  work only after its contract validated (BaseAgent) and the router saw no
  errors. A failed node routes to the error handler; downstream agents are
  simply never invoked on a poisoned state.
- **Two human-in-the-loop gates.** ``entity_gate`` fires when resolution is
  ambiguous (which vehicle books this notice?); ``exception_gate`` fires
  when validation finds critical issues (override or reject?). Both use
  ``interrupt()`` — the run parks in the checkpointer, survives restarts,
  and resumes with ``Command(resume=...)`` when a human decides.
- **Checkpointing after every node** (Postgres in production, in-memory in
  tests). A crash at any step resumes from the last completed node; the
  ingest agent's sha256 dedup makes replays idempotent.

Node order:
    ingest -> input_guard -> parse -> resolve -> [entity_gate] -> validate
    -> [exception_gate] -> analyze -> risk -> report -> complete
"""

from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src.agents.data_validator import DataValidatorAgent
from src.agents.document_ingest import DocumentIngestAgent, NoticeParserAgent
from src.agents.entity_resolver import EntityResolverAgent
from src.agents.portfolio_analyst import PortfolioAnalystAgent
from src.agents.report_generator import ReportGeneratorAgent
from src.agents.risk_monitor import RiskMonitorAgent
from src.config.settings import get_settings
from src.core.state import AgentState
from src.db.client import audit, db_conn
from src.guardrails.input_guard import InputGuardAgent
from src.observability.logger import get_logger

log = get_logger(component="orchestrator")


def mark_run(run_id: str | None, status: str, current_node: str | None = None,
             error: dict | None = None) -> None:
    """Reflect graph progress into workflow_runs (best-effort, like audit)."""
    if not run_id or not get_settings().database_url:
        return
    try:
        import json

        with db_conn() as conn:
            conn.execute(
                "update workflow_runs set status = %s,"
                " current_node = coalesce(%s, current_node),"
                " error = coalesce(%s::jsonb, error), updated_at = now()"
                " where id = %s",
                (status, current_node, json.dumps(error) if error else None, run_id),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("mark_run_failed", error=str(exc))


# --- human gates -----------------------------------------------------------


def entity_gate(state: AgentState) -> dict[str, Any]:
    """Ambiguous resolution: a human picks the destination entity."""
    resolution = state.get("resolution") or {}
    mark_run(state.get("run_id"), "awaiting_approval", "entity_gate")
    decision = interrupt({
        "gate": "entity_gate",
        "question": "Which entity should this notice be booked to?",
        "reason": resolution.get("reason"),
        "candidates": resolution.get("candidates", []),
        "notice": state.get("parsed"),
    })
    mark_run(state.get("run_id"), "running", "entity_gate")
    audit(state.get("run_id"), "entity_gate", "human_decision", payload=dict(decision))
    return {
        "human_decision": decision["decision"],
        "selected_entity_id": decision.get("selected_entity_id")
                              or state.get("selected_entity_id"),
        "needs_human": False,
    }


def exception_gate(state: AgentState) -> dict[str, Any]:
    """Critical validation issues: a human overrides or rejects the run."""
    validation = state.get("validation") or {}
    mark_run(state.get("run_id"), "awaiting_approval", "exception_gate")
    decision = interrupt({
        "gate": "exception_gate",
        "question": "Validation found critical issues. Override and continue, or reject?",
        "issues": validation.get("issues", []),
        "notice": state.get("parsed"),
    })
    mark_run(state.get("run_id"), "running", "exception_gate")
    audit(state.get("run_id"), "exception_gate", "human_decision", payload=dict(decision))
    return {"human_decision": decision["decision"], "needs_human": False}


# --- terminal nodes --------------------------------------------------------


def error_handler(state: AgentState) -> dict[str, Any]:
    errors = state.get("errors") or []
    last = errors[-1] if errors else {}
    log.error("run_failed", failed_agent=last.get("agent"), message=last.get("message"))
    audit(state.get("run_id"), "error_handler", "run_failed", level="error",
          payload={"errors": errors})
    mark_run(state.get("run_id"), "failed", last.get("agent"), error=last)
    return {}


def finalize_reject(state: AgentState) -> dict[str, Any]:
    audit(state.get("run_id"), "finalize", "run_rejected", level="warning")
    mark_run(state.get("run_id"), "rejected")
    if get_settings().database_url and state.get("document_id"):
        with db_conn() as conn:
            conn.execute(
                "update transactions set status = 'rejected'"
                " where document_id = %s and status = 'pending_review'",
                (state["document_id"],),
            )
    return {}


def complete(state: AgentState) -> dict[str, Any]:
    audit(state.get("run_id"), "finalize", "run_completed")
    mark_run(state.get("run_id"), "completed", "complete")
    return {}


# --- routers ---------------------------------------------------------------


def _errored(state: AgentState) -> bool:
    return bool(state.get("errors"))


def then(next_node: str):
    """Router factory: proceed unless the previous node recorded an error."""
    def route(state: AgentState) -> str:
        return "error_handler" if _errored(state) else next_node
    route.__name__ = f"route_to_{next_node}"
    return route


def after_resolve(state: AgentState) -> Literal["entity_gate", "validate", "error_handler"]:
    if _errored(state):
        return "error_handler"
    return "entity_gate" if state.get("needs_human") else "validate"


def after_entity_gate(state: AgentState) -> Literal["validate", "finalize_reject"]:
    return "validate" if state.get("human_decision") == "approved" else "finalize_reject"


def after_validate(state: AgentState) -> Literal["analyze", "exception_gate", "error_handler"]:
    if _errored(state):
        return "error_handler"
    passed = (state.get("validation") or {}).get("passed", False)
    return "analyze" if passed else "exception_gate"


def after_exception_gate(state: AgentState) -> Literal["analyze", "finalize_reject"]:
    return "analyze" if state.get("human_decision") == "approved" else "finalize_reject"


# --- graph -----------------------------------------------------------------


def build_graph(checkpointer=None):
    """Compile the workflow. Pass a PostgresSaver in production; defaults to
    an in-memory saver so tests exercise identical graph mechanics."""
    builder = StateGraph(AgentState)

    builder.add_node("ingest", DocumentIngestAgent())
    builder.add_node("input_guard", InputGuardAgent())
    builder.add_node("parse", NoticeParserAgent())
    builder.add_node("resolve", EntityResolverAgent())
    builder.add_node("entity_gate", entity_gate)
    builder.add_node("validate", DataValidatorAgent())
    builder.add_node("exception_gate", exception_gate)
    builder.add_node("analyze", PortfolioAnalystAgent())
    builder.add_node("risk", RiskMonitorAgent())
    builder.add_node("report", ReportGeneratorAgent())
    builder.add_node("error_handler", error_handler)
    builder.add_node("finalize_reject", finalize_reject)
    builder.add_node("complete", complete)

    builder.add_edge(START, "ingest")
    builder.add_conditional_edges("ingest", then("input_guard"))
    builder.add_conditional_edges("input_guard", then("parse"))
    builder.add_conditional_edges("parse", then("resolve"))
    builder.add_conditional_edges("resolve", after_resolve)
    builder.add_conditional_edges("entity_gate", after_entity_gate)
    builder.add_conditional_edges("validate", after_validate)
    builder.add_conditional_edges("exception_gate", after_exception_gate)
    builder.add_conditional_edges("analyze", then("risk"))
    builder.add_conditional_edges("risk", then("report"))
    builder.add_conditional_edges("report", then("complete"))
    builder.add_edge("error_handler", END)
    builder.add_edge("finalize_reject", END)
    builder.add_edge("complete", END)

    return builder.compile(checkpointer=checkpointer or InMemorySaver())
