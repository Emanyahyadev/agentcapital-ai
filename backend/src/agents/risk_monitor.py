"""Risk monitoring: the checks no single fund report can perform.

Look-through concentration is the flagship: five funds each holding 2-3% of
the same company is invisible fund-by-fund and a four-alarm fire in
aggregate. Also escalates unresolved reconciliation variances and imminent
capital-call deadlines into the risk record."""

from typing import Any

from src.agents.base import BaseAgent
from src.core.contracts import RiskFinding
from src.core.state import PolarisState
from src.db.client import audit, db_conn


def concentration_findings(
    exposures: list[tuple[str, float, list[str]]], limit_pct: float
) -> list[RiskFinding]:
    """exposures: (company, total % of NAV, [fund names]). Pure + testable."""
    findings = []
    for company, total_pct, funds in exposures:
        if total_pct >= limit_pct:
            findings.append(RiskFinding(
                kind="concentration",
                severity="critical" if total_pct >= limit_pct * 1.25 else "warning",
                message=f"look-through exposure to {company} is {total_pct:.1f}% of NAV "
                        f"across {len(funds)} funds (limit {limit_pct:.0f}%)",
                exposure_pct=round(total_pct, 2),
                entities=funds,
            ))
    return findings


class RiskMonitorAgent(BaseAgent):
    name = "risk_monitor"

    def execute(self, state: PolarisState) -> dict[str, Any]:
        limit_pct = self.settings.concentration_limit_pct * 100

        with db_conn() as conn:
            rows = conn.execute(
                """
                select c.name, sum(h.weight_pct) as total_pct,
                       array_agg(f.name order by h.weight_pct desc)
                from holdings h
                join entities c on c.id = h.company_entity_id
                join entities f on f.id = h.fund_entity_id
                group by c.name
                """
            ).fetchall()

        exposures = [(name, float(pct), funds) for name, pct, funds in rows]
        findings = concentration_findings(exposures, limit_pct)

        for issue in (state.get("validation") or {}).get("issues", []):
            if issue["code"] == "RECON_VARIANCE":
                findings.append(RiskFinding(
                    kind="reconciliation_variance", severity="critical",
                    message="unreconciled custodian variance on this run: "
                            + issue["message"],
                ))
            elif issue["code"] == "DEADLINE_IMMINENT":
                findings.append(RiskFinding(
                    kind="deadline", severity="warning", message=issue["message"],
                ))

        validated = [RiskFinding.model_validate(f).model_dump(mode="json")
                     for f in findings]
        # Carry the full findings (message, exposure, entities) so the console
        # can render an honest "why was this flagged" explanation.
        audit(state.get("run_id"), self.name, "risk_assessed",
              payload={"findings": validated})
        return {"risk_findings": validated}
