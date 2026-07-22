"""Structured logging: JSON lines in production, pretty console in dev.

Run and agent context is bound through contextvars, so every log line emitted
anywhere inside a workflow carries the correlating run_id — the property that
lets you reconstruct a failed 10-step run from logs alone.
"""

import logging

import structlog

from src.config.settings import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    renderer: structlog.typing.Processor
    if settings.env == "dev":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial: object) -> structlog.typing.FilteringBoundLogger:
    return structlog.get_logger().bind(**initial)


def bind_run_context(run_id: str, **extra: object) -> None:
    structlog.contextvars.bind_contextvars(run_id=run_id, **extra)


def clear_run_context() -> None:
    structlog.contextvars.clear_contextvars()
