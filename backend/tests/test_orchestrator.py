"""Graph mechanics under test with stubbed agent work: routing, both human
gates, error handling, and — the load-bearing one — resume across a
simulated process restart via the checkpointer."""

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.base import BaseAgent, PermanentFailure
from src.agents.data_validator import DataValidatorAgent
from src.agents.document_ingest import DocumentIngestAgent, NoticeParserAgent
from src.agents.entity_resolver import EntityResolverAgent
from src.agents.portfolio_analyst import PortfolioAnalystAgent
from src.agents.report_generator import ReportGeneratorAgent
from src.agents.risk_monitor import RiskMonitorAgent
from src.core import orchestrator
from src.core.contracts import (
    ParsedNotice,
    PortfolioSnapshot,
    Report,
    ResolutionResult,
    ValidationIssue,
    ValidationResult,
)

RAW_TEXT = "CAPITAL CALL NOTICE Fund: TechVantage Fund LP Amount Due: $850,000.00"

PARSED = ParsedNotice(
    doc_type="capital_call", fund_name_raw="TechVantage Fund LP", amount_usd=850_000.0
)
RESOLVED_CLEAN = ResolutionResult(
    candidates=[{"entity_id": "e-tech", "name": "TechVantage Fund LP", "kind": "fund",
                 "confidence": 0.99, "method": "exact"}],
    selected_entity_id="e-tech", reason="exact match",
)
RESOLVED_AMBIGUOUS = ResolutionResult(
    candidates=[
        {"entity_id": "e-par", "name": "Meridian Growth Fund IV", "kind": "fund",
         "confidence": 0.99, "method": "exact"},
        {"entity_id": "e-a", "name": "Meridian Growth Fund IV-A", "kind": "sub_fund",
         "confidence": 0.91, "method": "fuzzy"},
    ],
    needs_review=True, reason="parent fund with sub-fund mentions",
)
VALID_OK = ValidationResult(issues=[], passed=True)
VALID_FAIL = ValidationResult(
    issues=[ValidationIssue(code="RECON_VARIANCE", severity="critical", message="variance")],
    passed=False,
)


@pytest.fixture
def stub_agents(monkeypatch):
    """Replace agent work with deterministic stubs; graph mechanics stay real."""
    calls: list[str] = []

    def stub(cls, name, update):
        def execute(self, state):
            calls.append(name)
            return dict(update)
        monkeypatch.setattr(cls, "execute", execute)

    stub(DocumentIngestAgent, "ingest", {"document_id": "d1", "raw_text": RAW_TEXT})
    stub(NoticeParserAgent, "parse", {"parsed": PARSED})
    stub(EntityResolverAgent, "resolve",
         {"resolution": RESOLVED_CLEAN, "needs_human": False,
          "selected_entity_id": "e-tech"})
    stub(DataValidatorAgent, "validate", {"validation": VALID_OK, "needs_human": False})
    stub(PortfolioAnalystAgent, "analyze",
         {"portfolio": PortfolioSnapshot(as_of="2026-07-15", total_nav_usd=1.0)})
    stub(RiskMonitorAgent, "risk", {"risk_findings": []})
    stub(ReportGeneratorAgent, "report",
         {"report": Report(markdown="# Briefing\n" + "x" * 60, citations=[])})
    BaseAgent._breakers.clear()
    return calls


def invoke(graph, config, payload=None):
    return graph.invoke(
        payload if payload is not None else {"storage_path": "inbox/x.pdf"}, config
    )


def test_happy_path_runs_every_stage_in_order(stub_agents):
    graph = orchestrator.build_graph()
    result = invoke(graph, {"configurable": {"thread_id": "t-happy"}})
    assert stub_agents == ["ingest", "parse", "resolve", "validate",
                           "analyze", "risk", "report"]
    assert result["report"]["markdown"].startswith("# Briefing")
    assert not result.get("errors")


def test_ambiguous_resolution_interrupts_then_resumes_after_approval(
    stub_agents, monkeypatch
):
    def execute(self, state):
        stub_agents.append("resolve")
        return {"resolution": RESOLVED_AMBIGUOUS, "needs_human": True,
                "selected_entity_id": None}
    monkeypatch.setattr(EntityResolverAgent, "execute", execute)

    saver = InMemorySaver()
    config = {"configurable": {"thread_id": "t-hitl"}}
    graph = orchestrator.build_graph(saver)
    paused = invoke(graph, config)

    interrupts = paused["__interrupt__"]
    assert interrupts[0].value["gate"] == "entity_gate"
    assert "validate" not in stub_agents  # nothing downstream ran

    # Simulated crash: a brand-new graph instance over the same checkpointer.
    graph_after_restart = orchestrator.build_graph(saver)
    final = graph_after_restart.invoke(
        Command(resume={"decision": "approved", "selected_entity_id": "e-a"}), config
    )
    assert final["selected_entity_id"] == "e-a"
    assert final["report"]["markdown"].startswith("# Briefing")
    assert stub_agents[-4:] == ["validate", "analyze", "risk", "report"]


def test_validation_failure_routes_to_exception_gate_and_reject_stops_run(
    stub_agents, monkeypatch
):
    def execute(self, state):
        stub_agents.append("validate")
        return {"validation": VALID_FAIL, "needs_human": True}
    monkeypatch.setattr(DataValidatorAgent, "execute", execute)

    config = {"configurable": {"thread_id": "t-reject"}}
    graph = orchestrator.build_graph()
    paused = invoke(graph, config)
    assert paused["__interrupt__"][0].value["gate"] == "exception_gate"

    final = graph.invoke(Command(resume={"decision": "rejected"}), config)
    assert "analyze" not in stub_agents  # rejected runs never reach analysis
    assert "report" not in final


def test_agent_failure_routes_to_error_handler_not_downstream(stub_agents, monkeypatch):
    def execute(self, state):
        raise PermanentFailure("document vanished")
    monkeypatch.setattr(NoticeParserAgent, "execute", execute)

    graph = orchestrator.build_graph()
    result = invoke(graph, {"configurable": {"thread_id": "t-err"}})
    assert result["errors"][0]["agent"] == "notice_parser"
    # Failure cascade stopped: no enrichment or intelligence stage ran.
    assert stub_agents == ["ingest"]
