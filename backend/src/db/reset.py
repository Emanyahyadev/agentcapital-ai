"""Demo reset: clear all *processed* data so the demo scenarios can be
re-run — the sha256 idempotency guard (correctly) refuses to process the
same notice twice, so a demo session starts by wiping the transactional
tables. Master data (entities, custodian feed, holdings, prior positions)
is never touched."""

from src.db.client import db_conn

# Order matters: children before parents. Checkpointer tables are created
# by LangGraph's PostgresSaver.setup() and may not exist yet.
CLEAR = [
    "delete from audit_log",
    "delete from approvals",
    "delete from reports",
    "delete from transactions",
    "delete from doc_chunks",
    "delete from workflow_runs",
    "delete from documents",
    "delete from positions where source = 'calculated'",
    "delete from checkpoint_writes",
    "delete from checkpoint_blobs",
    "delete from checkpoints",
]


def reset_demo_data() -> dict[str, int]:
    cleared: dict[str, int] = {}
    with db_conn() as conn:
        for stmt in CLEAR:
            table = stmt.split("from ")[1].split()[0]
            try:
                cur = conn.execute(stmt)
                cleared[table] = cur.rowcount
            except Exception:  # noqa: BLE001 — checkpointer tables may not exist yet
                conn.rollback()
                cleared[table] = -1
    return cleared


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    print(json.dumps(reset_demo_data(), indent=2))
