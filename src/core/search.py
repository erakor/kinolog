"""Search: vector, BM25, and reciprocal rank fusion (RRF)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

from src.core.db import Database

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    item_id: int
    chunk_id: int | None = None
    score: float = 0.0
    title: str = ""
    year: int | None = None
    chunk_text: str = ""
    source: str = ""  # "vector", "bm25", "rrf"
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchFilters:
    item_type: str | None = None
    seen: bool | None = None
    liked: bool | None = None
    on_watchlist: bool | None = None
    year_min: int | None = None
    year_max: int | None = None
    country: str | None = None
    language: str | None = None
    decade: int | None = None

    def to_sql_conditions(self) -> tuple[str, list]:
        """Returns (WHERE clause fragments, params) for items table alias 'i'."""
        conditions = []
        params: list[Any] = []

        if self.item_type:
            conditions.append("i.item_type = ?")
            params.append(self.item_type)
        if self.year_min:
            conditions.append("i.year >= ?")
            params.append(self.year_min)
        if self.year_max:
            conditions.append("i.year <= ?")
            params.append(self.year_max)
        if self.decade:
            conditions.append("i.year >= ? AND i.year < ?")
            params.extend([self.decade, self.decade + 10])

        return " AND ".join(conditions), params

    def to_status_conditions(self) -> tuple[str, list]:
        """Returns (WHERE clause fragments, params) for user_status table alias 'us'."""
        conditions = []
        params: list[Any] = []

        if self.seen is not None:
            conditions.append("us.seen = ?")
            params.append(1 if self.seen else 0)
        if self.liked is not None:
            conditions.append("us.liked = ?")
            params.append(1 if self.liked else 0)
        if self.on_watchlist is not None:
            conditions.append("us.on_watchlist = ?")
            params.append(1 if self.on_watchlist else 0)

        return " AND ".join(conditions), params


def _format_fts_query(query: str) -> str:
    """Format user query into safe and effective FTS5 query with OR terms."""
    import re
    tokens = re.findall(r"[\w\u00C0-\u017F]+", query)
    if not tokens:
        return '""'
    return " OR ".join(f'"{t}"' for t in tokens)


def search_bm25(
    db: Database,
    query: str,
    limit: int = 20,
    filters: SearchFilters | None = None,
) -> list[SearchResult]:
    """BM25 search via FTS5."""
    sql = """
        SELECT c.id as chunk_id, c.item_id, c.text as chunk_text,
               i.title, i.year,
               bm25(chunks_fts, 1.0, 0.5) as score
        FROM chunks_fts
        JOIN chunks c ON chunks_fts.rowid = c.id
        JOIN items i ON c.item_id = i.id
    """
    params: list[Any] = []
    formatted = _format_fts_query(query)
    where_parts = ["chunks_fts MATCH ?"]
    params.append(formatted)

    if filters:
        item_cond, item_params = filters.to_sql_conditions()
        if item_cond:
            where_parts.append(item_cond)
            params.extend(item_params)

        status_cond, status_params = filters.to_status_conditions()
        if status_cond:
            sql += " LEFT JOIN user_status us ON i.id = us.item_id"
            where_parts.append(status_cond)
            params.extend(status_params)

    sql += " WHERE " + " AND ".join(where_parts)
    sql += " ORDER BY score LIMIT ?"
    params.append(limit)

    try:
        rows = db.execute(sql, tuple(params)).fetchall()
    except Exception as e:
        logger.warning("BM25 search failed: %s", e)
        return []

    results = []
    for row in rows:
        results.append(SearchResult(
            item_id=row["item_id"],
            chunk_id=row["chunk_id"],
            score=-row["score"],  # BM25 returns negative scores in SQLite
            title=row["title"],
            year=row["year"],
            chunk_text=row["chunk_text"],
            source="bm25",
        ))
    return results


def search_vector(
    db: Database,
    query_embedding: np.ndarray,
    model_name: str,
    limit: int = 20,
    filters: SearchFilters | None = None,
) -> list[SearchResult]:
    """Vector similarity search via sqlite-vec."""
    if not db.vec_available:
        logger.warning("Vector search unavailable: sqlite-vec not loaded")
        return []

    vec_table = f"vec_{model_name}"

    # Basic vector search
    sql = f"""
        SELECT v.chunk_id, v.distance,
               c.item_id, c.text as chunk_text,
               i.title, i.year
        FROM {vec_table} v
        JOIN chunks c ON v.chunk_id = c.id
        JOIN items i ON c.item_id = i.id
    """
    params: list[Any] = []
    where_parts = [f"v.embedding MATCH ? AND k = ?"]
    params.append(query_embedding.tobytes())
    params.append(limit * 3)  # fetch more, then filter

    if filters:
        item_cond, item_params = filters.to_sql_conditions()
        if item_cond:
            where_parts.append(item_cond)
            params.extend(item_params)

        status_cond, status_params = filters.to_status_conditions()
        if status_cond:
            sql += " LEFT JOIN user_status us ON i.id = us.item_id"
            where_parts.append(status_cond)
            params.extend(status_params)

    sql += " WHERE " + " AND ".join(where_parts)
    sql += f" ORDER BY v.distance LIMIT ?"
    params.append(limit)

    try:
        rows = db.execute(sql, tuple(params)).fetchall()
    except Exception as e:
        logger.warning("Vector search failed: %s", e)
        return []

    results = []
    for row in rows:
        # Convert distance to similarity (cosine distance -> cosine similarity)
        similarity = 1.0 - row["distance"]
        results.append(SearchResult(
            item_id=row["item_id"],
            chunk_id=row["chunk_id"],
            score=similarity,
            title=row["title"],
            year=row["year"],
            chunk_text=row["chunk_text"],
            source="vector",
        ))
    return results


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
    model_name: str = "bge_m3",
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
        results.append(SearchResult(
            item_id=r.item_id,
            chunk_id=r.chunk_id,
            score=score,
            title=r.title,
            year=r.year,
            chunk_text=r.chunk_text,
            source="rrf",
        ))

    return results


def search(
    db: Database,
    query: str,
    model: Any | None = None,
    model_name: str = "bge_m3",
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
        results = search_rrf(
            db, query, query_embedding, model_name, limit=limit, filters=filters
        )
    else:
        raise ValueError(f"Unknown search mode: {mode}")

    if dedupe_items:
        results = _dedupe_by_item(results)

    return results[:limit]
