"""Seed realistic synthetic data for the Whitmore Family Office portfolio.

The data encodes the three scenarios the system is built to catch:

1. Ambiguity — "Meridian Growth Fund IV" has sub-funds IV-A and IV-B, and
   capital calls arrive addressed to the parent name.
2. Conflict — the custodian feed shows TechVantage Fund LP's position cut by
   $1.2M on 2026-07-15, while the distribution PDF that arrives the same day
   is issued by the similarly named TechVantage *Opportunities* LP.
3. Hidden concentration — five unrelated funds each hold 2-3% of NeuroAI Inc,
   a combined 14.2% look-through exposure no single fund report shows.

Idempotent: safe to run repeatedly.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import psycopg  # noqa: E402

from src.config.settings import get_settings  # noqa: E402

AS_OF_PRIOR = date(2026, 6, 30)
AS_OF_FEED = date(2026, 7, 15)

# name, kind, parent_name, aliases, sector
ENTITIES = [
    ("Meridian Growth Fund IV", "fund", None, ["Fund IV", "Meridian IV"], None),
    ("Meridian Growth Fund IV-A", "sub_fund", "Meridian Growth Fund IV", ["Fund IV-A"], None),
    ("Meridian Growth Fund IV-B", "sub_fund", "Meridian Growth Fund IV", ["Fund IV-B"], None),
    ("TechVantage Fund LP", "fund", None, ["TechVantage", "TechVantage Fund"], None),
    ("TechVantage Opportunities LP", "fund", None, ["TechVantage Opportunities"], None),
    ("Northgate Ventures IX", "fund", None, ["Northgate IX"], None),
    ("Crestline Real Estate Partners VIII", "fund", None, ["Crestline VIII", "CREP VIII"], None),
    ("Halcyon Growth Equity III", "fund", None, ["Halcyon III"], None),
    ("Auren Ventures V", "fund", None, ["Auren V"], None),
    ("NeuroAI Inc", "company", None, ["NeuroAI"], "Artificial Intelligence"),
    ("QuantumLeap Systems", "company", None, [], "Quantum Computing"),
    ("GreenField Renewables", "company", None, [], "Clean Energy"),
    ("Vertex Biotech", "company", None, [], "Biotechnology"),
    ("Solara Energy", "company", None, [], "Clean Energy"),
]

# entity_name -> market value on 2026-06-30 (custodian-sourced)
POSITIONS_PRIOR = {
    "Meridian Growth Fund IV-A": 9_800_000,
    "Meridian Growth Fund IV-B": 6_400_000,
    "TechVantage Fund LP": 1_500_000,
    "TechVantage Opportunities LP": 5_200_000,
    "Northgate Ventures IX": 12_300_000,
    "Crestline Real Estate Partners VIII": 11_800_000,
    "Halcyon Growth Equity III": 8_900_000,
    "Auren Ventures V": 6_100_000,
}

# The 2026-07-15 feed: TechVantage Fund LP is down exactly $1.2M — the same
# amount the TechVantage *Opportunities* distribution notice claims. The
# validator has to notice that the money moved in the WRONG fund.
CUSTODIAN_FEED = {
    "Meridian Growth Fund IV-A": 9_800_000,
    "Meridian Growth Fund IV-B": 6_400_000,
    "TechVantage Fund LP": 300_000,
    "TechVantage Opportunities LP": 5_200_000,
    "Northgate Ventures IX": 12_450_000,
    "Crestline Real Estate Partners VIII": 11_800_000,
    "Halcyon Growth Equity III": 8_950_000,
    "Auren Ventures V": 6_100_000,
}

# fund, company, % of total portfolio NAV — NeuroAI sums to 14.2%
HOLDINGS = [
    ("Northgate Ventures IX", "NeuroAI Inc", 3.1),
    ("Halcyon Growth Equity III", "NeuroAI Inc", 2.8),
    ("Auren Ventures V", "NeuroAI Inc", 2.9),
    ("Meridian Growth Fund IV-A", "NeuroAI Inc", 2.6),
    ("TechVantage Fund LP", "NeuroAI Inc", 2.8),
    ("Northgate Ventures IX", "QuantumLeap Systems", 1.9),
    ("Halcyon Growth Equity III", "Vertex Biotech", 2.2),
    ("Crestline Real Estate Partners VIII", "Solara Energy", 1.4),
    ("Auren Ventures V", "GreenField Renewables", 1.7),
]


def seed(conn: psycopg.Connection) -> None:
    ids: dict[str, str] = {}
    for name, kind, parent, aliases, sector in ENTITIES:
        row = conn.execute(
            """
            insert into entities (name, kind, parent_id, aliases, sector)
            values (%s, %s, %s, %s, %s)
            on conflict (name) do update set aliases = excluded.aliases
            returning id
            """,
            (name, kind, ids.get(parent) if parent else None, aliases, sector),
        ).fetchone()
        ids[name] = row[0]

    for name, value in POSITIONS_PRIOR.items():
        conn.execute(
            """
            insert into positions (entity_id, as_of, market_value_usd, source)
            values (%s, %s, %s, 'custodian')
            on conflict (entity_id, as_of, source) do update
                set market_value_usd = excluded.market_value_usd
            """,
            (ids[name], AS_OF_PRIOR, value),
        )

    for i, (name, value) in enumerate(CUSTODIAN_FEED.items(), start=1):
        conn.execute(
            """
            insert into custodian_feed (account_ref, entity_name, position_value_usd, as_of)
            values (%s, %s, %s, %s)
            on conflict (account_ref, as_of) do update
                set position_value_usd = excluded.position_value_usd
            """,
            (f"NBK-{i:04d}", name, value, AS_OF_FEED),
        )

    for fund, company, pct in HOLDINGS:
        conn.execute(
            """
            insert into holdings (fund_entity_id, company_entity_id, weight_pct, as_of)
            values (%s, %s, %s, %s)
            on conflict (fund_entity_id, company_entity_id, as_of) do update
                set weight_pct = excluded.weight_pct
            """,
            (ids[fund], ids[company], pct, AS_OF_PRIOR),
        )


def main() -> None:
    settings = get_settings()
    if not settings.database_url:
        sys.exit("DATABASE_URL is not set — put the Supabase session-pooler URL in backend/.env")
    with psycopg.connect(settings.database_url) as conn:
        seed(conn)
        conn.commit()
    print("seed complete")


if __name__ == "__main__":
    main()
