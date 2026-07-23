"""Thinking-capable models return content as a list of typed blocks; the
report must be clean markdown, not a stringified list of dicts."""

from src.core.llm import content_to_text


def test_plain_string_passthrough():
    assert content_to_text("## Report\nhello") == "## Report\nhello"


def test_list_of_text_blocks_is_joined():
    content = [
        {"type": "text", "text": "## Summary"},
        {"type": "text", "text": "Body line."},
    ]
    assert content_to_text(content) == "## Summary\nBody line."


def test_reasoning_and_signature_blocks_are_dropped():
    content = [
        {"type": "thinking", "thinking": "internal chain of thought"},
        {"type": "text", "text": "## Briefing", "extras": {"signature": "abc123"}},
    ]
    out = content_to_text(content)
    assert out == "## Briefing"
    assert "chain of thought" not in out
    assert "signature" not in out


def test_bare_strings_in_list():
    assert content_to_text(["a", "b"]) == "a\nb"
