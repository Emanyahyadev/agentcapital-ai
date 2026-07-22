"""Pooled Postgres access + the audit-trail writer.

The audit trail is append-only and best-effort by design: an audit INSERT
failing must never take down the pipeline it is describing, so ``audit``
swallows and logs its own failures instead of raising.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from src.config.settings import get_settings
from src.observability.logger import get_logger

log = get_logger(component="db")

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=0,
            max_size=4,
            open=True,
            kwargs={"connect_timeout": 10},
        )
    return _pool


@contextmanager
def db_conn() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn


def audit(
    run_id: str | None,
    agent: str,
    event: str,
    level: str = "info",
    payload: dict[str, Any] | None = None,
) -> None:
    settings = get_settings()
    if not settings.database_url:  # unit tests / local without DB
        return
    try:
        with db_conn() as conn:
            conn.execute(
                "insert into audit_log (run_id, agent, event, level, payload)"
                " values (%s, %s, %s, %s, %s)",
                (run_id, agent, event, level, Jsonb(payload or {})),
            )
    except Exception as exc:  # noqa: BLE001 — audit must never kill the pipeline
        log.warning("audit_write_failed", event=event, error=str(exc))
