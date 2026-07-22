from src.config.settings import Settings


def test_settings_defaults_are_sane():
    s = Settings(_env_file=None)
    assert s.embedding_dim == 768
    assert 0 < s.entity_match_review_floor < s.entity_match_auto_accept <= 1
    assert s.max_retries >= 1


def test_settings_read_env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gemini-test")
    s = Settings(_env_file=None)
    assert s.llm_model == "gemini-test"
