"""Per-agent execution telemetry.

Token usage is accumulated through a contextvar that the LLM helpers write
to and the base agent reads around each ``execute`` call — giving real,
per-agent token counts without threading a meter through every signature.
Node execution inside a LangGraph invoke is synchronous on one task, so the
contextvar scopes correctly to the agent currently running.
"""

import contextvars

_token_meter: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "token_meter", default=None
)


def reset_tokens() -> None:
    """Begin a fresh capture window (called by the base agent per attempt)."""
    _token_meter.set({"input": 0, "output": 0})


def record_tokens(input_tokens: int | None, output_tokens: int | None) -> None:
    """Add a model call's usage to the current window (called by llm helpers)."""
    meter = _token_meter.get()
    if meter is not None:
        meter["input"] += int(input_tokens or 0)
        meter["output"] += int(output_tokens or 0)


def collected_tokens() -> dict:
    meter = _token_meter.get()
    return dict(meter) if meter else {"input": 0, "output": 0}
