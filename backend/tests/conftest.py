"""Test isolation: unit tests must never touch a real database, cache, or
LLM — regardless of what the developer's local .env contains. Environment
variables take priority over dotenv values in pydantic-settings, so forcing
them empty here guarantees the graceful-skip paths in db.client and
retrieval are what tests exercise."""

import pytest

from src.config.settings import get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
