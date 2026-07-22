"""LLM factory. Temperature 0 everywhere — extraction and reporting want
determinism, not creativity. Flash-Lite handles cheap steps to stay inside
the free tier's rate limits."""

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel

from src.config.settings import get_settings


def chat_model(lite: bool = False) -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.llm_model_lite if lite else settings.llm_model,
        google_api_key=settings.google_api_key or None,
        temperature=0.0,
        max_retries=0,  # BaseAgent owns retry policy; don't stack retry layers
    )


def extract_structured[M: BaseModel](
    model_cls: type[M], system: str, user: str, lite: bool = False
) -> M:
    """One-shot structured extraction; output arrives already schema-validated."""
    llm = chat_model(lite=lite).with_structured_output(model_cls)
    return llm.invoke([("system", system), ("human", user)])  # type: ignore[return-value]
