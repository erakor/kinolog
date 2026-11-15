"""Ranker scoring by the nearest hearted exemplar."""

from __future__ import annotations

from kinolog.config import DEFAULT_MODEL, DEFAULT_STRATEGY
from kinolog.store import Database
from kinolog.taste.base import register
from kinolog.taste.data import _get_item_embeddings
from kinolog.taste.scores import TasteScore

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


@register("nearest_exemplar")
def rank_nearest_exemplar(
    db: Database,
    candidate_ids: list[int],
    heart_ids: list[int],
    model_name: str = DEFAULT_MODEL,
    strategy: str = DEFAULT_STRATEGY,
) -> list[TasteScore]:
    """Score = max cosine similarity to any heart."""
    heart_embeddings = _get_item_embeddings(db, heart_ids, model_name, strategy)
    if not heart_embeddings:
        return []

    heart_vecs = np.array(list(heart_embeddings.values()))
    candidate_embeddings = _get_item_embeddings(db, candidate_ids, model_name, strategy)
    scores = []

    for item_id, vec in candidate_embeddings.items():
        cosines = heart_vecs @ vec  # (n_hearts,)
        max_cosine = float(np.max(cosines))
        scores.append(TasteScore(item_id=item_id, score=max_cosine, method="nearest_exemplar"))

    scores.sort(key=lambda x: x.score, reverse=True)
    return scores
