"""LLM factory. Temperature 0 everywhere — extraction and reporting want
determinism, not creativity. Flash-Lite handles cheap steps to stay inside
the free tier's rate limits. Every call records its token usage through the
telemetry meter so per-agent token counts are real, not estimated.

Model fallback: the primary model (Flash) and Flash-Lite have *separate*
free-tier quotas. When the primary returns a rate-limit / quota error, the
call transparently retries once on Flash-Lite rather than failing the run —
the "fall back when the primary is unavailable" pattern, at the model layer.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from src.config.settings import get_settings
from src.core.telemetry import record_tokens
from src.observability.logger import get_logger

log = get_logger(component="llm")

_RATE_MARKERS = ("429", "resource_exhausted", "resourceexhausted", "quota", "rate limit")


def is_rate_limited(exc: Exception) -> bool:
    return any(m in f"{exc}".lower() for m in _RATE_MARKERS)


def chat_model(lite: bool = False) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.llm_model_lite if lite else settings.llm_model,
        google_api_key=settings.google_api_key or None,
        temperature=0.0,
        max_retries=0,  # BaseAgent owns retry policy; don't stack retry layers
    )


def _record(message) -> None:
    usage = getattr(message, "usage_metadata", None)
    if usage:
        record_tokens(usage.get("input_tokens"), usage.get("output_tokens"))


def content_to_text(content) -> str:
    """Flatten an LLM message's content to plain text.

    Newer (thinking-capable) Gemini models return content as a list of typed
    blocks — text, plus reasoning/signature blocks — instead of a bare string.
    Join the text blocks and drop the rest, so downstream always gets clean
    markdown rather than a stringified list of dicts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") in (None, "text"):
                text = block.get("text")
                if text:
                    parts.append(text)
        return "\n".join(parts)
    return str(content)


def _with_fallback(call, lite: bool):
    """Run `call(lite)`; on a rate-limit error from the primary model, retry
    once on Flash-Lite (separate quota). Re-raise anything else."""
    try:
        return call(lite)
    except Exception as exc:  # noqa: BLE001 — inspect, then re-raise or fall back
        if lite or not is_rate_limited(exc):
            raise
        log.warning("llm_rate_limited_falling_back_to_lite", error=str(exc)[:120])
        return call(True)


def extract_structured[M: BaseModel](
    model_cls: type[M], system: str, user: str, lite: bool = False
) -> M:
    """One-shot structured extraction; output arrives already schema-validated.
    include_raw keeps the underlying AIMessage so token usage is captured."""

    def call(use_lite: bool) -> M:
        llm = chat_model(lite=use_lite).with_structured_output(model_cls, include_raw=True)
        result = llm.invoke([("system", system), ("human", user)])
        _record(result.get("raw"))
        return result["parsed"]  # type: ignore[return-value]

    return _with_fallback(call, lite)


def invoke_text(messages: list, lite: bool = False) -> str:
    """Free-form completion that records token usage and returns plain text."""

    def call(use_lite: bool) -> str:
        response = chat_model(lite=use_lite).invoke(messages)
        _record(response)
        return content_to_text(response.content)

    return _with_fallback(call, lite)
