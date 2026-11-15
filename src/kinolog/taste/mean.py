"""Rankers scoring by similarity to the mean (or top-k mean) of hearted items."""

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


@register("mean_heart")
def rank_mean_heart(
    db: Database,
    candidate_ids: list[int],
    heart_ids: list[int],
    model_name: str = DEFAULT_MODEL,
    strategy: str = DEFAULT_STRATEGY,
) -> list[TasteScore]:
    """Mean of heart vectors baseline."""
    heart_embeddings = _get_item_embeddings(db, heart_ids, model_name, strategy)
    if not heart_embeddings:
        return []

    # Compute mean heart vector
    heart_vecs = np.array(list(heart_embeddings.values()))
    mean_vec = heart_vecs.mean(axis=0)
    norm = np.linalg.norm(mean_vec)
    if norm > 0:
        mean_vec = mean_vec / norm

    # Score candidates
    candidate_embeddings = _get_item_embeddings(db, candidate_ids, model_name, strategy)
    scores = []

    for item_id, vec in candidate_embeddings.items():
        cosine = float(np.dot(mean_vec, vec))
        scores.append(TasteScore(item_id=item_id, score=cosine, method="mean_heart"))

    scores.sort(key=lambda x: x.score, reverse=True)
    return scores


def rank_top_k_mean(
    db: Database,
    candidate_ids: list[int],
    heart_ids: list[int],
    k: int = 3,
    model_name: str = DEFAULT_MODEL,
    strategy: str = DEFAULT_STRATEGY,
) -> list[TasteScore]:
    """Score = mean of top-k cosine similarities to hearts."""
    heart_embeddings = _get_item_embeddings(db, heart_ids, model_name, strategy)
    if not heart_embeddings:
        return []

    heart_vecs = np.array(list(heart_embeddings.values()))
    candidate_embeddings = _get_item_embeddings(db, candidate_ids, model_name, strategy)
    scores = []

    actual_k = min(k, len(heart_vecs))

    for item_id, vec in candidate_embeddings.items():
        cosines = heart_vecs @ vec
        top_k = np.sort(cosines)[-actual_k:]
        mean_score = float(np.mean(top_k))
        scores.append(TasteScore(item_id=item_id, score=mean_score, method=f"top_{k}_mean"))

    scores.sort(key=lambda x: x.score, reverse=True)
    return scores


@register("top_3_mean")
def top_3_mean(db, cands, hearts, **kw):
    return rank_top_k_mean(db, cands, hearts, k=3, **kw)
