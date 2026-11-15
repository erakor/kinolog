"""Hearts recall: how well a taste ranker recovers held-out hearted films."""

from __future__ import annotations

import logging
import random
import statistics
from collections.abc import Callable

from kinolog.eval.metrics import mrr, recall_at_k
from kinolog.eval.runner import EvalResult
from kinolog.store import Database

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


logger = logging.getLogger(__name__)


# --- Hearts recall eval ---


def eval_hearts_recall(
    db: Database,
    rank_fn: Callable,
    n_splits: int = 10,
    holdout_fraction: float = 0.2,
    k_values: tuple[int, ...] = (20, 50),
    first_heart_date: str | None = None,
    min_hearts: int = 5,
    seed: int = 42,
) -> list[EvalResult]:
    """
    Hearts recall evaluation with multiple random splits.

    rank_fn(db, candidate_ids, heart_ids, **kwargs) -> list[TasteScore]
    """
    all_hearts = db.execute(
        "SELECT item_id FROM user_status WHERE liked = 1"
    ).fetchall()
    heart_ids = [r["item_id"] for r in all_hearts]

    if len(heart_ids) < min_hearts:
        logger.warning("Too few hearts (%d) for meaningful eval", len(heart_ids))
        return []

    # Get candidates: all seen films after first-heart date
    candidates_sql = "SELECT i.id FROM items i JOIN user_status us ON i.id = us.item_id WHERE us.seen = 1"
    if first_heart_date:
        candidates_sql += " AND us.seen_date >= ?"
        all_candidates = [
            r["id"] for r in db.execute(candidates_sql, (first_heart_date,)).fetchall()
        ]
    else:
        all_candidates = [r["id"] for r in db.execute(candidates_sql).fetchall()]

    rng = random.Random(seed)
    split_results: dict[str, list[float]] = {}

    for split_idx in range(n_splits):
        rng.shuffle(heart_ids)
        n_holdout = max(1, int(len(heart_ids) * holdout_fraction))
        holdout = set(heart_ids[:n_holdout])
        train_hearts = heart_ids[n_holdout:]

        # Candidates include holdout hearts plus non-hearts
        candidates = [c for c in all_candidates if c not in set(train_hearts)]

        # Rank
        scores = rank_fn(db, candidates, train_hearts)
        ranked_ids = [s.item_id for s in scores]

        for k in k_values:
            key = f"recall@{k}"
            if key not in split_results:
                split_results[key] = []
            split_results[key].append(recall_at_k(ranked_ids, holdout, k))

        # MRR
        if "mrr" not in split_results:
            split_results["mrr"] = []
        split_results["mrr"].append(mrr(ranked_ids, holdout))

    eval_results = []
    for metric_name, values in split_results.items():
        if not values:
            continue
        if np is not None:
            arr = np.array(values)
            val = float(arr.mean())
            sd = float(arr.std())
        else:
            val = statistics.mean(values)
            sd = statistics.stdev(values) if len(values) > 1 else 0.0

        eval_results.append(EvalResult(
            suite="hearts_recall",
            metric=metric_name,
            value=val,
            stdev=sd,
            config={
                "n_splits": n_splits,
                "holdout_fraction": holdout_fraction,
                "n_hearts": len(heart_ids),
                "n_candidates": len(all_candidates),
            },
        ))

    return eval_results
