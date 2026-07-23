"""Data validation: the tripwire between "an agent said so" and "the books
say so".

Runs after entity resolution and cross-checks the parsed notice against
independent sources — prior positions and the custodian bank feed. This is
where the conflicting-record case is handled: a distribution whose money
visibly moved in a DIFFERENT fund's custodian position is flagged critical
and routed to a human, with the evidence attached.
"""

from datetime import date, timedelta
from typing import Any

from src.agents.base import BaseAgent
from src.core.contracts import ValidationIssue, ValidationResult
from src.core.state import AgentState
from src.db.client import audit, db_conn


def reconcile_distribution(
    amount: float,
    prior_value: float | None,
    feed_value: float | None,
    peer_moves: list[tuple[str, float]],
    tolerance: float,
) -> list[ValidationIssue]:
    """Pure reconciliation logic, unit-testable without a database.

    Expected: feed position ≈ prior position − distribution amount.
    peer_moves: (entity_name, drop) for OTHER entities whose position fell
    since the prior snapshot — evidence for a mis-attributed distribution.
    """
    issues: list[ValidationIssue] = []
    if prior_value is None or feed_value is None:
        issues.append(ValidationIssue(
            code="RECON_NO_DATA", severity="warning",
            message="cannot reconcile: missing prior position or custodian feed row",
            details={"prior_value": prior_value, "feed_value": feed_value},
        ))
        return issues

    expected = prior_value - amount
    variance = feed_value - expected
    if abs(variance) / amount > tolerance:
        suspects = [
            {"entity": name, "position_drop": drop}
            for name, drop in peer_moves
            if abs(drop - amount) / amount <= tolerance
        ]
        message = (
            f"custodian feed does not reflect this distribution: expected "
            f"{expected:,.0f}, feed shows {feed_value:,.0f} (variance {variance:+,.0f})"
        )
        if suspects:
            message += (
                f" — a position drop matching the amount was observed in "
                f"{suspects[0]['entity']!r} instead; the notice may be attributed "
                f"to the wrong fund"
            )
        issues.append(ValidationIssue(
            code="RECON_VARIANCE", severity="critical", message=message,
            details={"expected": expected, "feed_value": feed_value,
                     "variance": variance, "suspects": suspects},
        ))
    return issues


class DataValidatorAgent(BaseAgent):
    name = "data_validator"
    output_key = "validation"
    output_model = ValidationResult

    def execute(self, state: AgentState) -> dict[str, Any]:
        parsed = state["parsed"]
        entity_id = state.get("selected_entity_id")
        issues: list[ValidationIssue] = []

        if not entity_id:
            issues.append(ValidationIssue(
                code="UNKNOWN_ENTITY", severity="critical",
                message="no resolved entity — cannot book this transaction",
            ))
            return self._finish(state, issues)

        with db_conn() as conn:
            entity_name = conn.execute(
                "select name from entities where id = %s", (entity_id,)
            ).fetchone()[0]

            dup = conn.execute(
                """
                select id from transactions
                where entity_id = %s and txn_type = %s and amount_usd = %s
                  and coalesce(due_date, effective_date)
                      is not distinct from coalesce(%s::date, %s::date)
                """,
                (entity_id, parsed["doc_type"], parsed["amount_usd"],
                 parsed.get("due_date"), parsed.get("effective_date")),
            ).fetchone()
            if dup:
                issues.append(ValidationIssue(
                    code="DUPLICATE_NOTICE", severity="critical",
                    message=f"an identical {parsed['doc_type']} is already booked "
                            f"({dup[0]}) — double-funding guard",
                    details={"existing_transaction": str(dup[0])},
                ))

            if parsed["doc_type"] == "distribution":
                issues += self._reconcile(conn, entity_name, parsed)
            elif parsed["doc_type"] == "capital_call":
                issues += self._check_deadline(parsed)

            confidence = self._top_confidence(state)
            conn.execute(
                """
                insert into transactions
                    (entity_id, document_id, txn_type, amount_usd, due_date,
                     effective_date, status, confidence)
                values (%s, %s, %s, %s, %s, %s, 'pending_review', %s)
                """,
                (entity_id, state.get("document_id"), parsed["doc_type"],
                 parsed["amount_usd"], parsed.get("due_date"),
                 parsed.get("effective_date"), confidence),
            )

        return self._finish(state, issues)

    def _reconcile(self, conn, entity_name: str, parsed: dict) -> list[ValidationIssue]:
        amount = parsed["amount_usd"]
        prior = conn.execute(
            """
            select p.market_value_usd from positions p
            join entities e on e.id = p.entity_id
            where e.name = %s and p.source = 'custodian'
            order by p.as_of desc limit 1
            """,
            (entity_name,),
        ).fetchone()
        feed = conn.execute(
            "select position_value_usd from custodian_feed"
            " where entity_name = %s order by as_of desc limit 1",
            (entity_name,),
        ).fetchone()
        # Any peer whose feed position dropped since its prior snapshot is
        # evidence when the numbers don't add up for THIS entity.
        peer_rows = conn.execute(
            """
            select f.entity_name,
                   p.market_value_usd - f.position_value_usd as drop
            from custodian_feed f
            join entities e on e.name = f.entity_name
            join positions p on p.entity_id = e.id and p.source = 'custodian'
            where f.entity_name <> %s
              and p.market_value_usd > f.position_value_usd
            """,
            (entity_name,),
        ).fetchall()
        return reconcile_distribution(
            amount,
            float(prior[0]) if prior else None,
            float(feed[0]) if feed else None,
            [(name, float(drop)) for name, drop in peer_rows],
            self.settings.reconciliation_variance_pct,
        )

    def _check_deadline(self, parsed: dict) -> list[ValidationIssue]:
        due = parsed.get("due_date")
        if due is None:
            return [ValidationIssue(
                code="MISSING_DUE_DATE", severity="warning",
                message="capital call without a due date — deadline cannot be tracked",
            )]
        due_date = date.fromisoformat(due) if isinstance(due, str) else due
        if due_date <= date.today() + timedelta(days=7):
            return [ValidationIssue(
                code="DEADLINE_IMMINENT", severity="warning",
                message=f"capital call due {due_date.isoformat()} — inside the "
                        f"7-day funding window",
                details={"due_date": due_date.isoformat()},
            )]
        return []

    def _top_confidence(self, state: AgentState) -> float | None:
        candidates = (state.get("resolution") or {}).get("candidates") or []
        selected = state.get("selected_entity_id")
        for cand in candidates:
            if cand["entity_id"] == selected:
                return cand["confidence"]
        return None

    def _finish(self, state: AgentState, issues: list[ValidationIssue]) -> dict[str, Any]:
        result = ValidationResult(
            issues=issues,
            passed=not any(i.severity == "critical" for i in issues),
        )
        audit(state.get("run_id"), self.name, "validation_complete",
              level="info" if result.passed else "warning",
              payload={"passed": result.passed,
                       "issues": [(i.code, i.severity) for i in issues]})
        return {"validation": result, "needs_human": not result.passed}
