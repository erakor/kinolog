"""Vector (semantic) search over a sqlite-vec table."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from kinolog.retrieval.filters import SearchFilters
from kinolog.retrieval.results import SearchResult
from kinolog.store import Database

if TYPE_CHECKING:
    import numpy as np


logger = logging.getLogger(__name__)


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
    where_parts = ["v.embedding MATCH ? AND k = ?"]
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
    sql += " ORDER BY v.distance LIMIT ?"
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
