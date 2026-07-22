"""Chunking and vector plumbing are pure logic — tested without a database."""

from src.retrieval.chunker import chunk_text
from src.retrieval.embeddings import _normalize
from src.retrieval.retriever import _as_vector_literal


def test_chunks_respect_size_and_cover_all_text():
    paras = [f"Paragraph {i}: " + "capital call notice details. " * 8 for i in range(10)]
    text = "\n\n".join(paras)
    chunks = chunk_text(text, size=500, overlap=100)
    assert all(len(c) <= 500 + 100 for c in chunks)
    for i in range(10):  # every paragraph survives chunking
        assert any(f"Paragraph {i}:" in c for c in chunks)


def test_oversized_single_paragraph_is_hard_split():
    text = "x" * 3000
    chunks = chunk_text(text, size=800, overlap=150)
    assert len(chunks) > 1
    assert all(len(c) <= 800 for c in chunks)


def test_empty_text_yields_no_chunks():
    assert chunk_text("   \n\n  ") == []


def test_normalize_produces_unit_vectors():
    vec = _normalize([3.0, 4.0])
    assert abs((vec[0] ** 2 + vec[1] ** 2) - 1.0) < 1e-9


def test_vector_literal_is_pgvector_syntax():
    literal = _as_vector_literal([0.5, -0.25])
    assert literal.startswith("[") and literal.endswith("]")
    assert literal.count(",") == 1
