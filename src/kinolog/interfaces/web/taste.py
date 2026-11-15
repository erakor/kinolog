"""Web-layer cache around core taste scoring (invalidated by any mutation)."""

from __future__ import annotations

from kinolog.core.taste import taste_scores
from kinolog.interfaces.web.state import AppState


def cached_taste_scores(
    state: AppState, candidate_ids: list[int], ranker: str = "nearest_exemplar"
) -> dict[int, float]:
    heart_ids = state.db.get_heart_ids()
    key = (ranker, tuple(heart_ids), tuple(sorted(candidate_ids)))
    cached = state.taste_cache.get(key)
    if cached is None:
        cached = state.taste_cache[key] = taste_scores(state.db, candidate_ids, ranker, heart_ids)
    return cached
