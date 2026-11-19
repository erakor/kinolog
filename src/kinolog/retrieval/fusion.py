"""Reciprocal rank fusion of BM25 and vector search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kinolog.config import DEFAULT_MODEL
from kinolog.retrieval.bm25 import search_bm25
from kinolog.retrieval.filters import SearchFilters
from kinolog.retrieval.results import SearchResult
from kinolog.retrieval.vector import search_vector
from kinolog.store import Database

if TYPE_CHECKING:
    import numpy as np


def _dedupe_by_item(results: list[SearchResult]) -> list[SearchResult]:
    """Keep only the best result per item."""
    seen: dict[int, SearchResult] = {}
    for r in results:
        if r.item_id not in seen or r.score > seen[r.item_id].score:
            seen[r.item_id] = r
    return sorted(seen.values(), key=lambda x: x.score, reverse=True)


def search_rrf(
    db: Database,
    query: str,
    query_embedding: np.ndarray | None = None,
    model_name: str = DEFAULT_MODEL,
    limit: int = 20,
    k: int = 60,
    filters: SearchFilters | None = None,
    bm25_weight: float = 1.0,
    vector_weight: float = 1.0,
) -> list[SearchResult]:
    """
    Reciprocal Rank Fusion of BM25 and vector search.

    RRF score = sum over systems of weight / (k + rank_in_system)
    """
    bm25_results = search_bm25(db, query, limit=limit * 2, filters=filters)

    vector_results = []
    if query_embedding is not None:
        vector_results = search_vector(
            db, query_embedding, model_name, limit=limit * 2, filters=filters
        )

    # Build RRF scores
    rrf_scores: dict[int, float] = {}  # chunk_id -> score
    chunk_data: dict[int, SearchResult] = {}

    for rank, r in enumerate(bm25_results):
        rrf_scores[r.chunk_id] = rrf_scores.get(r.chunk_id, 0) + bm25_weight / (k + rank + 1)
        chunk_data[r.chunk_id] = r

    for rank, r in enumerate(vector_results):
        rrf_scores[r.chunk_id] = rrf_scores.get(r.chunk_id, 0) + vector_weight / (k + rank + 1)
        if r.chunk_id not in chunk_data:
            chunk_data[r.chunk_id] = r

    # Sort by RRF score
    sorted_chunks = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for chunk_id, score in sorted_chunks[:limit]:
        r = chunk_data[chunk_id]
        results.append(
            SearchResult(
                item_id=r.item_id,
                chunk_id=r.chunk_id,
                score=score,
                title=r.title,
                year=r.year,
                chunk_text=r.chunk_text,
                source="rrf",
            )
        )

    return results
