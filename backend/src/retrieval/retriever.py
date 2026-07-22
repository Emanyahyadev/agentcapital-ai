"""Hybrid retrieval over ingested filings.

Ranking is done entirely in Postgres by the hybrid_search() SQL function
(002_rag.sql): dense cosine ranking and full-text ranking are fused with
Reciprocal Rank Fusion. Hybrid matters here because finance queries are
exact-token-heavy ("Fund IV-A", "$1,200,000", "NGV9-2026-044") — pure
vector search blurs precisely the tokens that distinguish sub-funds."""

from typing import Any

from src.db.client import db_conn
from src.observability.logger import get_logger
from src.retrieval.chunker import chunk_text
from src.retrieval.embeddings import embed_query, embed_texts

log = get_logger(component="retriever")


def _as_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in vec) + "]"


def index_document(document_id: str, text: str) -> int:
    """Chunk + embed + upsert a document into doc_chunks. Idempotent."""
    chunks = chunk_text(text)
    if not chunks:
        return 0
    vectors = embed_texts(chunks)
    with db_conn() as conn:
        for i, (content, vec) in enumerate(zip(chunks, vectors, strict=True)):
            conn.execute(
                """
                insert into doc_chunks (document_id, chunk_index, content, embedding)
                values (%s, %s, %s, %s::vector)
                on conflict (document_id, chunk_index) do update
                    set content = excluded.content, embedding = excluded.embedding
                """,
                (document_id, i, content, _as_vector_literal(vec)),
            )
    log.info("document_indexed", document_id=document_id, chunks=len(chunks))
    return len(chunks)


def search_chunks(query: str, match_count: int = 8) -> list[dict[str, Any]]:
    vec = embed_query(query)
    with db_conn() as conn:
        rows = conn.execute(
            "select chunk_id, document_id, content, score"
            " from hybrid_search(%s, %s::vector, %s)",
            (query, _as_vector_literal(vec), match_count),
        ).fetchall()
    return [
        {"chunk_id": r[0], "document_id": str(r[1]), "content": r[2], "score": float(r[3])}
        for r in rows
    ]
