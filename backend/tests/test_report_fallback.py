"""The deterministic report fallback must produce a valid briefing from
pipeline facts alone, so a run always yields a report even with no LLM."""

from src.agents.report_generator import deterministic_report
from src.core.contracts import Report


def _state():
    return {
        "parsed": {
            "doc_type": "capital_call",
            "fund_name_raw": "TechVantage Fund LP",
            "amount_usd": 850000.0,
            "due_date": "2026-08-05",
            "notice_no": "TVF-2026-018",
        },
        "validation": {"issues": [], "passed": True},
        "portfolio": {"as_of": "2026-07-15", "total_nav_usd": 61000000.0},
        "risk_findings": [{
            "kind": "concentration", "severity": "critical",
            "message": "look-through exposure to NeuroAI Inc is 14.2% of NAV",
            "entities": ["Northgate Ventures IX", "Auren Ventures V"],
        }],
        "human_decision": None,
    }


def test_fallback_report_is_a_valid_contract():
    md = deterministic_report(_state())
    Report(markdown=md, citations=[])  # must satisfy the contract (min length etc.)
    assert "TechVantage Fund LP" in md
    assert "$850,000.00" in md
    assert "NeuroAI Inc" in md
    assert "fallback mode" in md


def test_fallback_reflects_critical_validation():
    state = _state()
    state["validation"] = {
        "passed": False,
        "issues": [{"code": "RECON_VARIANCE", "severity": "critical",
                    "message": "custodian feed does not reflect this distribution"}],
    }
    md = deterministic_report(state)
    assert "Critical issues found" in md
    assert "RECON_VARIANCE" in md
    assert "Resolve the flagged validation issues" in md


def test_fallback_handles_missing_fields():
    md = deterministic_report({"parsed": {}, "validation": {}, "portfolio": {}})
    assert len(md) >= 50  # still a usable briefing
    assert "Unknown fund" in md
