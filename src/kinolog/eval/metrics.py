"""Evaluation metrics: recall@k, MRR, hit@k, nDCG."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def recall_at_k(
    ranked_ids: list[int],
    relevant_ids: set[int],
    k: int,
) -> float:
    """Fraction of relevant items found in top-k."""
    if not relevant_ids:
        return 0.0
    found = len(set(ranked_ids[:k]) & relevant_ids)
    return found / len(relevant_ids)


def hit_at_k(
    ranked_ids: list[int],
    target_id: int,
    k: int,
) -> int:
    """1 if target_id is in top-k, else 0."""
    return 1 if target_id in ranked_ids[:k] else 0


def mrr(
    ranked_ids: list[int],
    relevant_ids: set[int],
) -> float:
    """Mean Reciprocal Rank: 1/rank of first relevant item."""
    for i, item_id in enumerate(ranked_ids):
        if item_id in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def ndcg_at_k(
    ranked_ids: list[int],
    relevance: dict[int, float],
    k: int,
) -> float:
    """Normalized Discounted Cumulative Gain at k."""
    import math

    dcg = 0.0
    for i, item_id in enumerate(ranked_ids[:k]):
        rel = relevance.get(item_id, 0.0)
        dcg += rel / math.log2(i + 2)

    # Ideal DCG
    ideal_rels = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(rel / math.log2(i + 2) for i, rel in enumerate(ideal_rels))

    return dcg / idcg if idcg > 0 else 0.0
