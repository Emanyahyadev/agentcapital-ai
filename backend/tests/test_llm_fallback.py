"""Model fallback: a rate-limited primary call retries on Flash-Lite; other
errors and already-lite calls propagate unchanged."""

import pytest

from src.core.llm import _with_fallback, is_rate_limited


def test_rate_limit_detection():
    assert is_rate_limited(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert is_rate_limited(RuntimeError("You exceeded your current quota"))
    assert not is_rate_limited(RuntimeError("invalid api key"))


def test_falls_back_to_lite_on_rate_limit():
    calls = []

    def call(use_lite):
        calls.append(use_lite)
        if not use_lite:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return "lite-result"

    assert _with_fallback(call, lite=False) == "lite-result"
    assert calls == [False, True]  # primary attempted, then lite


def test_non_rate_limit_error_is_not_retried():
    calls = []

    def call(use_lite):
        calls.append(use_lite)
        raise RuntimeError("malformed request")

    with pytest.raises(RuntimeError, match="malformed"):
        _with_fallback(call, lite=False)
    assert calls == [False]  # no fallback on non-rate-limit errors


def test_already_lite_does_not_double_fall_back():
    calls = []

    def call(use_lite):
        calls.append(use_lite)
        raise RuntimeError("429 quota")

    with pytest.raises(RuntimeError):
        _with_fallback(call, lite=True)
    assert calls == [True]  # already on lite; nowhere to fall back
