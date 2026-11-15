"""Taste scores: the score type, availability checks and the ``taste_scores`` entry point."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kinolog.config import DEFAULT_MODEL, DEFAULT_RANKER
from kinolog.store import Database
from kinolog.taste.base import RANKERS

logger = logging.getLogger(__name__)


@dataclass
class TasteScore:
    item_id: int
    score: float
    title: str = ""
    year: int | None = None
    method: str = ""


class TasteUnavailableError(Exception):
    """Taste scoring cannot run (no vectors, no hearts, no embeddings)."""


def taste_available(db: Database, model_name: str = DEFAULT_MODEL) -> bool:
    """Rankers read stored embeddings, so they need the vec table, not the model."""
    if not db.vec_available:
        return False
    table = f"vec_{model_name}"
    row = db.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).fetchone()
    return row is not None


def taste_scores(
    db: Database,
    candidate_ids: list[int],
    ranker: str = DEFAULT_RANKER,
    heart_ids: list[int] | None = None,
) -> dict[int, float]:
    """Taste score per candidate (only those with embeddings), trained on hearted films.

    Raises TasteUnavailableError with a human-readable reason instead of returning garbage,
    so callers (web, CLI, eval) can degrade consistently.
    """
    fn = RANKERS.get(ranker)
    if fn is None:
        raise TasteUnavailableError(f"Unknown ranker: {ranker}")
    if not taste_available(db):
        raise TasteUnavailableError("Vector search or embeddings are not available")
    hearts = db.get_heart_ids() if heart_ids is None else heart_ids
    if not hearts:
        raise TasteUnavailableError("No hearted films yet")
    try:
        scores = fn(db, list(candidate_ids), hearts)
    except Exception as e:  # missing vec table, numpy, etc.
        logger.warning("Taste ranking failed: %s", e)
        raise TasteUnavailableError("Taste ranking failed (are embeddings built?)") from e
    if not scores and candidate_ids:
        raise TasteUnavailableError("No embeddings for hearted films")
    return {s.item_id: s.score for s in scores}
