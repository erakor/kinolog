"""Taste rankers: score items by taste affinity from hearted films."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

from kinolog.core.db import Database

logger = logging.getLogger(__name__)


@dataclass
class TasteScore:
    item_id: int
    score: float
    title: str = ""
    year: int | None = None
    method: str = ""


def _get_item_embeddings(
    db: Database,
    item_ids: list[int],
    model_name: str = "bge_m3",
    strategy: str = "whole",
    rollup: str = "mean",
) -> dict[int, Any]:
    """
    Get a single embedding per item, aggregated from its chunks.

    rollup: "mean", "max", or "first"
    """
    if np is None:
        raise RuntimeError("numpy is required for embedding-based taste ranking")
    vec_table = f"vec_{model_name}"
    result = {}

    for item_id in item_ids:
        rows = db.execute(
            f"""SELECT v.embedding FROM {vec_table} v
                JOIN chunks c ON v.chunk_id = c.id
                WHERE c.item_id = ? AND c.strategy = ?
                ORDER BY c.ord""",
            (item_id, strategy),
        ).fetchall()

        if not rows:
            continue

        embeddings = np.array([
            np.frombuffer(row["embedding"], dtype=np.float32)
            for row in rows
        ])

        if rollup == "mean":
            vec = embeddings.mean(axis=0)
        elif rollup == "max":
            vec = embeddings.max(axis=0)
        elif rollup == "first":
            vec = embeddings[0]
        else:
            vec = embeddings.mean(axis=0)

        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        result[item_id] = vec

    return result


def _get_heart_ids(db: Database, first_heart_date: str | None = None) -> list[int]:
    """Get item IDs of hearted films."""
    rows = db.execute(
        "SELECT item_id FROM user_status WHERE liked = 1"
    ).fetchall()
    return [r["item_id"] for r in rows]


def _get_candidate_ids(
    db: Database,
    first_heart_date: str | None = None,
    exclude_ids: set[int] | None = None,
    item_type: str = "film",
) -> list[int]:
    """Get candidate item IDs for taste ranking."""
    rows = db.execute(
        "SELECT id FROM items WHERE item_type = ?", (item_type,)
    ).fetchall()
    ids = [r["id"] for r in rows]
    if exclude_ids:
        ids = [i for i in ids if i not in exclude_ids]
    return ids


# --- Taste Rankers ---


def rank_mean_heart(
    db: Database,
    candidate_ids: list[int],
    heart_ids: list[int],
    model_name: str = "bge_m3",
    strategy: str = "whole",
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


def rank_nearest_exemplar(
    db: Database,
    candidate_ids: list[int],
    heart_ids: list[int],
    model_name: str = "bge_m3",
    strategy: str = "whole",
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


def rank_top_k_mean(
    db: Database,
    candidate_ids: list[int],
    heart_ids: list[int],
    k: int = 3,
    model_name: str = "bge_m3",
    strategy: str = "whole",
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


def rank_prototypes(
    db: Database,
    candidate_ids: list[int],
    heart_ids: list[int],
    n_clusters: int = 5,
    model_name: str = "bge_m3",
    strategy: str = "whole",
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
        scores.append(TasteScore(
            item_id=item_id, score=max_cosine,
            method=f"prototypes_k{actual_k}",
        ))

    scores.sort(key=lambda x: x.score, reverse=True)
    return scores


# Registry
RANKERS = {
    "mean_heart": rank_mean_heart,
    "nearest_exemplar": rank_nearest_exemplar,
    "top_3_mean": lambda db, cands, hearts, **kw: rank_top_k_mean(db, cands, hearts, k=3, **kw),
    "prototypes_4": lambda db, cands, hearts, **kw: rank_prototypes(db, cands, hearts, n_clusters=4, **kw),
    "prototypes_5": lambda db, cands, hearts, **kw: rank_prototypes(db, cands, hearts, n_clusters=5, **kw),
    "prototypes_6": lambda db, cands, hearts, **kw: rank_prototypes(db, cands, hearts, n_clusters=6, **kw),
}


class TasteUnavailableError(Exception):
    """Taste scoring cannot run (no vectors, no hearts, no embeddings)."""


def taste_available(db: Database, model_name: str = "bge_m3") -> bool:
    """Rankers read stored embeddings, so they need the vec table, not the model."""
    if not db.vec_available:
        return False
    table = f"vec_{model_name}"
    row = db.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).fetchone()
    return row is not None


def taste_scores(
    db: Database,
    candidate_ids: list[int],
    ranker: str = "nearest_exemplar",
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
