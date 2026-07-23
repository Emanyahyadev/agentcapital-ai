"""Portfolio analysis: recompute NAV from the latest custodian feed.

Deliberately zero-LLM — NAV is arithmetic over sourced numbers, and numbers
an LLM "computed" cannot be audited. The snapshot is persisted as
'calculated' positions so every report's figures are reproducible."""

from typing import Any

from src.agents.base import BaseAgent, PermanentFailure
from src.core.contracts import PortfolioSnapshot, PositionLine
from src.core.state import AgentState
from src.db.client import audit, db_conn


class PortfolioAnalystAgent(BaseAgent):
    name = "portfolio_analyst"
    output_key = "portfolio"
    output_model = PortfolioSnapshot

    def execute(self, state: AgentState) -> dict[str, Any]:
        with db_conn() as conn:
            rows = conn.execute(
                """
                select distinct on (f.entity_name)
                       e.id, e.name, f.position_value_usd, f.as_of
                from custodian_feed f
                join entities e on e.name = f.entity_name
                order by f.entity_name, f.as_of desc
                """
            ).fetchall()
            if not rows:
                raise PermanentFailure("custodian feed is empty — no NAV to compute")

            as_of = max(row[3] for row in rows)
            lines = [
                PositionLine(entity_id=str(r[0]), name=r[1], market_value_usd=float(r[2]))
                for r in rows
            ]
            snapshot = PortfolioSnapshot(
                as_of=as_of,
                total_nav_usd=round(sum(line.market_value_usd for line in lines), 2),
                lines=sorted(lines, key=lambda line: -line.market_value_usd),
            )

            for line in snapshot.lines:
                conn.execute(
                    """
                    insert into positions (entity_id, as_of, market_value_usd, source)
                    values (%s, %s, %s, 'calculated')
                    on conflict (entity_id, as_of, source) do update
                        set market_value_usd = excluded.market_value_usd
                    """,
                    (line.entity_id, as_of, line.market_value_usd),
                )

        audit(state.get("run_id"), self.name, "nav_computed",
              payload={"as_of": str(snapshot.as_of),
                       "total_nav_usd": snapshot.total_nav_usd,
                       "positions": len(snapshot.lines)})
        return {"portfolio": snapshot}
