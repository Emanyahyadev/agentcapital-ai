"""Central configuration. Every env var the system reads is declared here."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase / Postgres — DATABASE_URL must be the session-mode pooler (port 5432);
    # the direct db host is IPv6-only and unreachable from most free-tier hosts.
    database_url: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    inbox_bucket: str = "inbox"

    # LLM
    google_api_key: str = ""
    llm_model: str = "gemini-2.5-flash"
    llm_model_lite: str = "gemini-2.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = 768

    # Upstash Redis (REST)
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # App
    env: str = "dev"
    log_level: str = "INFO"

    # Agent resilience defaults
    max_retries: int = 3
    retry_base_delay_s: float = 2.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown_s: float = 60.0

    # Decision thresholds (tuned in evals — see evals/)
    entity_match_auto_accept: float = 0.93
    entity_match_review_floor: float = 0.60
    reconciliation_variance_pct: float = 0.10
    concentration_limit_pct: float = 0.10


@lru_cache
def get_settings() -> Settings:
    return Settings()
