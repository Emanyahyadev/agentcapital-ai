"""Report generation: the only place free-form LLM prose is produced — and
it is grounded exclusively in facts already validated upstream. The numbers
come from state; the LLM's job is narration, not computation. Citations are
assembled in code, never invented by the model."""

import json
from typing import Any

from src.agents.base import BaseAgent
from src.core.contracts import Report
from src.core.llm import chat_model
from src.core.state import PolarisState
from src.db.client import audit, db_conn

REPORT_SYSTEM_PROMPT = """You write concise intelligence briefings for a family \
office investment committee.

You are given structured facts as JSON: a parsed fund notice, entity resolution,
validation results, a portfolio NAV snapshot, and risk findings. Write a Markdown
briefing with sections: Summary, Transaction Detail, Validation & Reconciliation,
Portfolio Impact, Risk Flags, Recommended Actions.

Hard rules:
- Use ONLY numbers present in the input JSON. Never compute, extrapolate, or invent
  figures. If a value is absent, say so.
- Lead with what needs a decision. Flag critical items with '⚠'.
- Keep it under 500 words."""


class ReportGeneratorAgent(BaseAgent):
    name = "report_generator"
    output_key = "report"
    output_model = Report

    def execute(self, state: PolarisState) -> dict[str, Any]:
        context_chunks = self._retrieve_context(state)
        facts = {
            "notice": state.get("parsed"),
            "resolution": state.get("resolution"),
            "human_decision": state.get("human_decision"),
            "validation": state.get("validation"),
            "portfolio": state.get("portfolio"),
            "risk_findings": state.get("risk_findings"),
            "supporting_excerpts": [c["content"] for c in context_chunks],
        }
        response = chat_model().invoke([
            ("system", REPORT_SYSTEM_PROMPT),
            ("human", json.dumps(facts, default=str)),
        ])
        markdown = response.content if isinstance(response.content, str) else str(response.content)

        citations: list[dict[str, Any]] = [{
            "type": "source_document",
            "document_id": state.get("document_id"),
            "storage_path": state.get("storage_path"),
        }]
        citations += [
            {"type": "chunk", "chunk_id": c["chunk_id"],
             "document_id": c["document_id"], "score": c["score"]}
            for c in context_chunks
        ]
        report = Report(markdown=markdown, citations=citations)

        with db_conn() as conn:
            conn.execute(
                "insert into reports (run_id, markdown, citations)"
                " values (%s, %s, %s::jsonb)",
                (state["run_id"], report.markdown, json.dumps(report.citations)),
            )
            # The books are only touched once everything upstream agreed —
            # validation passed, or a human explicitly approved the exception.
            validation_passed = (state.get("validation") or {}).get("passed", False)
            if validation_passed or state.get("human_decision") == "approved":
                conn.execute(
                    "update transactions set status = 'confirmed'"
                    " where document_id = %s and status = 'pending_review'",
                    (state.get("document_id"),),
                )

        audit(state.get("run_id"), self.name, "report_generated",
              payload={"chars": len(report.markdown), "citations": len(report.citations)})
        return {"report": report}

    def _retrieve_context(self, state: PolarisState) -> list[dict[str, Any]]:
        """Pull supporting excerpts from previously ingested filings via the
        hybrid retriever. Soft dependency: reporting proceeds without RAG
        rather than failing the run."""
        parsed = state.get("parsed") or {}
        query = f"{parsed.get('fund_name_raw', '')} {parsed.get('doc_type', '')}".strip()
        if not query:
            return []
        try:
            from src.retrieval.retriever import search_chunks

            return search_chunks(query, match_count=4)
        except Exception as exc:  # noqa: BLE001 — RAG is enrichment, not a dependency
            self.log.warning("context_retrieval_skipped", error=str(exc))
            return []
