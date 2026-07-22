"""LLM factory. Temperature 0 everywhere — extraction and reporting want
determinism, not creativity. Flash-Lite handles cheap steps to stay inside
the free tier's rate limits. Every call records its token usage through the
telemetry meter so per-agent token counts are real, not estimated."""

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from src.config.settings import get_settings
from src.core.telemetry import record_tokens


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


def extract_structured[M: BaseModel](
    model_cls: type[M], system: str, user: str, lite: bool = False
) -> M:
    """One-shot structured extraction; output arrives already schema-validated.
    include_raw keeps the underlying AIMessage so token usage is captured."""
    llm = chat_model(lite=lite).with_structured_output(model_cls, include_raw=True)
    result = llm.invoke([("system", system), ("human", user)])
    _record(result.get("raw"))
    return result["parsed"]  # type: ignore[return-value]


def invoke_text(messages: list, lite: bool = False) -> str:
    """Free-form completion that records token usage and returns plain text."""
    response = chat_model(lite=lite).invoke(messages)
    _record(response)
    return response.content if isinstance(response.content, str) else str(response.content)
