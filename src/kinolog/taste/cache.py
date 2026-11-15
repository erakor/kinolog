"""Memoised taste scores, for callers that rank the same candidates repeatedly.

The key includes the heart ids, so a changed set of hearts never returns stale scores;
``clear()`` additionally drops everything after any mutation that can change taste inputs.
"""

from __future__ import annotations

from typing import Any

from kinolog.config import DEFAULT_RANKER
from kinolog.store import Database
from kinolog.taste import taste_scores


class TasteCache:
    def __init__(self) -> None:
        self._entries: dict[Any, dict[int, float]] = {}

    def scores(
        self, db: Database, candidate_ids: list[int], ranker: str = DEFAULT_RANKER
    ) -> dict[int, float]:
        heart_ids = db.get_heart_ids()
        key = (ranker, tuple(heart_ids), tuple(sorted(candidate_ids)))
        cached = self._entries.get(key)
        if cached is None:
            cached = self._entries[key] = taste_scores(db, candidate_ids, ranker, heart_ids)
        return cached

    def clear(self) -> None:
        self._entries.clear()
