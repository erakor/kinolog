"""Search dispatcher by mode."""

from __future__ import annotations

from typing import Any

from kinolog.config import DEFAULT_MODEL
from kinolog.retrieval.bm25 import search_bm25
from kinolog.retrieval.filters import SearchFilters
from kinolog.retrieval.fusion import _dedupe_by_item, search_rrf
from kinolog.retrieval.results import SearchResult
from kinolog.retrieval.vector import search_vector
from kinolog.store import Database


def search(
    db: Database,
    query: str,
    model: Any | None = None,
    model_name: str = DEFAULT_MODEL,
    mode: str = "rrf",
    limit: int = 20,
    filters: SearchFilters | None = None,
    dedupe_items: bool = True,
) -> list[SearchResult]:
    """
    High-level search function.

    Args:
        mode: "bm25", "vector", or "rrf"
        model: embedding model instance (needed for vector/rrf)
        dedupe_items: if True, keep only best result per item
    """
    query_embedding = None
    if mode in ("vector", "rrf") and model is not None:
        query_embedding = model.encode([query])[0]

    if mode == "bm25":
        results = search_bm25(db, query, limit=limit, filters=filters)
    elif mode == "vector":
        if query_embedding is None:
            raise ValueError("Vector search requires an embedding model")
        results = search_vector(db, query_embedding, model_name, limit=limit, filters=filters)
    elif mode == "rrf":
        results = search_rrf(db, query, query_embedding, model_name, limit=limit, filters=filters)
    else:
        raise ValueError(f"Unknown search mode: {mode}")

    if dedupe_items:
        results = _dedupe_by_item(results)

    return results[:limit]
