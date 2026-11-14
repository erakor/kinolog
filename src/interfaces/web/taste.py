"""Taste scoring for the web layer: cached, with a clear 'unavailable' signal."""

from __future__ import annotations

import logging

from src.core.db import Database
from src.interfaces.web.state import AppState

logger = logging.getLogger(__name__)


class TasteUnavailableError(Exception):
    pass


def taste_scores(
    state: AppState, db: Database, candidate_ids: list[int], ranker: str = "nearest_exemplar"
) -> dict[int, float]:
    """Taste score per candidate item (only those with embeddings). Cached until a mutation."""
    from src.core.taste import RANKERS

    fn = RANKERS.get(ranker)
    if fn is None:
        raise TasteUnavailableError(f"Unknown ranker: {ranker}")
    if not state.taste_available(db):
        raise TasteUnavailableError("Vector search or embeddings are not available")
    heart_ids = db.get_heart_ids()
    if not heart_ids:
        raise TasteUnavailableError("No hearted films yet")
    key = (ranker, tuple(heart_ids), tuple(sorted(candidate_ids)))
    cached = state.taste_cache.get(key)
    if cached is not None:
        return cached
    try:
        scores = fn(db, list(candidate_ids), heart_ids)
    except Exception as e:  # missing vec table, numpy, etc.
        logger.warning("Taste ranking failed: %s", e)
        raise TasteUnavailableError("Taste ranking failed (are embeddings built?)") from e
    if not scores and candidate_ids:
        raise TasteUnavailableError("No embeddings for hearted films")
    result = {s.item_id: s.score for s in scores}
    state.taste_cache[key] = result
    return result
