"""Gemini embeddings at 768 dimensions, with an Upstash Redis cache.

Two details that matter:
- Truncated (non-3072d) Gemini embeddings are NOT unit-normalized; cosine
  distance needs normalization, so we normalize before storing/querying.
- Embeddings are cached by content hash in Upstash — re-indexing a document
  (checkpoint replays, reruns) must not burn free-tier quota.
"""

import hashlib
import json
import math

from google import genai
from google.genai import types

from src.config.settings import get_settings
from src.observability.logger import get_logger

log = get_logger(component="embeddings")


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cache():
    settings = get_settings()
    if not (settings.upstash_redis_rest_url and settings.upstash_redis_rest_token):
        return None
    try:
        from upstash_redis import Redis

        return Redis(url=settings.upstash_redis_rest_url,
                     token=settings.upstash_redis_rest_token)
    except Exception as exc:  # noqa: BLE001 — cache is an optimization, never a dependency
        log.warning("upstash_unavailable", error=str(exc))
        return None


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    settings = get_settings()
    cache = _cache()
    out: list[list[float] | None] = [None] * len(texts)
    misses: list[int] = []

    for i, text in enumerate(texts):
        key = f"emb:{task_type}:{hashlib.sha1(text.encode()).hexdigest()}"
        cached = cache.get(key) if cache else None
        if cached:
            out[i] = json.loads(cached)
        else:
            misses.append(i)

    if misses:
        client = genai.Client(api_key=settings.google_api_key)
        response = client.models.embed_content(
            model=settings.embedding_model,
            contents=[texts[i] for i in misses],
            config=types.EmbedContentConfig(
                output_dimensionality=settings.embedding_dim,
                task_type=task_type,
            ),
        )
        for i, emb in zip(misses, response.embeddings, strict=True):
            vec = _normalize(list(emb.values))
            out[i] = vec
            if cache:
                key = f"emb:{task_type}:{hashlib.sha1(texts[i].encode()).hexdigest()}"
                cache.set(key, json.dumps(vec), ex=60 * 60 * 24 * 7)

    log.info("embedded", total=len(texts), cache_hits=len(texts) - len(misses))
    return out  # type: ignore[return-value]


def embed_query(text: str) -> list[float]:
    return embed_texts([text], task_type="RETRIEVAL_QUERY")[0]
