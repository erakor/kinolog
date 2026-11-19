"""Ranker scoring by k-means prototypes of hearted items."""

from __future__ import annotations

from kinolog.config import DEFAULT_MODEL, DEFAULT_STRATEGY
from kinolog.store import Database
from kinolog.taste.base import register
from kinolog.taste.data import _get_item_embeddings
from kinolog.taste.mean import rank_mean_heart
from kinolog.taste.scores import TasteScore

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


def rank_prototypes(
    db: Database,
    candidate_ids: list[int],
    heart_ids: list[int],
    n_clusters: int = 5,
    model_name: str = DEFAULT_MODEL,
    strategy: str = DEFAULT_STRATEGY,
) -> list[TasteScore]:
    """K-means prototypes: score = max cosine to any cluster centroid."""
    from sklearn.cluster import KMeans

    heart_embeddings = _get_item_embeddings(db, heart_ids, model_name, strategy)
    if len(heart_embeddings) < n_clusters:
        return rank_mean_heart(db, candidate_ids, heart_ids, model_name, strategy)

    heart_vecs = np.array(list(heart_embeddings.values()))

    # Cluster hearts
    actual_k = min(n_clusters, len(heart_vecs))
    kmeans = KMeans(n_clusters=actual_k, random_state=42, n_init=10)
    kmeans.fit(heart_vecs)
    centroids = kmeans.cluster_centers_

    # Normalize centroids
    norms = np.linalg.norm(centroids, axis=1, keepdims=True)
    centroids = centroids / np.maximum(norms, 1e-8)

    # Score candidates
    candidate_embeddings = _get_item_embeddings(db, candidate_ids, model_name, strategy)
    scores = []

    for item_id, vec in candidate_embeddings.items():
        cosines = centroids @ vec
        max_cosine = float(np.max(cosines))
        scores.append(
            TasteScore(
                item_id=item_id,
                score=max_cosine,
                method=f"prototypes_k{actual_k}",
            )
        )

    scores.sort(key=lambda x: x.score, reverse=True)
    return scores


@register("prototypes_4")
def prototypes_4(db, cands, hearts, **kw):
    return rank_prototypes(db, cands, hearts, n_clusters=4, **kw)


@register("prototypes_5")
def prototypes_5(db, cands, hearts, **kw):
    return rank_prototypes(db, cands, hearts, n_clusters=5, **kw)


@register("prototypes_6")
def prototypes_6(db, cands, hearts, **kw):
    return rank_prototypes(db, cands, hearts, n_clusters=6, **kw)
