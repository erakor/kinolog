"""BM25 keyword search over the FTS5 index."""

from __future__ import annotations

import logging
from typing import Any

from kinolog.retrieval.filters import SearchFilters
from kinolog.retrieval.results import SearchResult
from kinolog.store import Database

logger = logging.getLogger(__name__)


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
        results.append(
            SearchResult(
                item_id=row["item_id"],
                chunk_id=row["chunk_id"],
                score=-row["score"],  # BM25 returns negative scores in SQLite
                title=row["title"],
                year=row["year"],
                chunk_text=row["chunk_text"],
                source="bm25",
            )
        )
    return results
