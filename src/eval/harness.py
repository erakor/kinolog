"""Evaluation harness: runs suites and logs results."""

from __future__ import annotations

import json
import logging
import random
import statistics
from dataclasses import dataclass
from typing import Any, Callable

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

from src.core.db import Database
from src.eval.metrics import hit_at_k, mrr, recall_at_k

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    suite: str
    metric: str
    value: float
    stdev: float | None = None
    config: dict | None = None
    details: list[dict] | None = None


# --- Known-item eval ---


def load_known_item_queries(path: str = "src/eval/datasets/known_items.json") -> list[dict]:
    """Load known-item queries from JSON file."""
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        logger.warning("Known-item query file not found: %s", path)
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def eval_known_items(
    db: Database,
    search_fn: Callable,
    queries: list[dict] | None = None,
    k_values: tuple[int, ...] = (5, 10, 20),
) -> list[EvalResult]:
    """
    Evaluate known-item retrieval.

    Each query has: {"query": str, "target_title": str, "target_year": int | None}
    """
    if queries is None:
        queries = load_known_item_queries()
    if not queries:
        logger.warning("No known-item queries to evaluate")
        return []

    results_by_k: dict[int, list[int]] = {k: [] for k in k_values}
    mrr_values: list[float] = []
    details = []

    for q in queries:
        query_text = q["query"]
        target_title = q["target_title"]
        target_year = q.get("target_year")

        # Find the target item
        target = db.execute(
            "SELECT id FROM items WHERE title = ? AND year IS ?",
            (target_title, target_year),
        ).fetchone()

        if not target:
            # Try partial match
            target = db.execute(
                "SELECT id FROM items WHERE title LIKE ?",
                (f"%{target_title}%",),
            ).fetchone()

        if not target:
            logger.warning("Target not found: '%s' (%s)", target_title, target_year)
            continue

        target_id = target["id"]

        # Run search
        search_results = search_fn(query_text)
        result_ids = [r.item_id for r in search_results]

        # Compute metrics
        for k in k_values:
            results_by_k[k].append(hit_at_k(result_ids, target_id, k))

        mrr_val = mrr(result_ids, {target_id})
        mrr_values.append(mrr_val)

        details.append({
            "query": query_text,
            "target": target_title,
            "hit_5": hit_at_k(result_ids, target_id, 5),
            "mrr": mrr_val,
            "rank": result_ids.index(target_id) + 1 if target_id in result_ids else None,
        })

    eval_results = []
    for k in k_values:
        vals = results_by_k[k]
        if vals:
            eval_results.append(EvalResult(
                suite="known_items",
                metric=f"hit@{k}",
                value=sum(vals) / len(vals),
                config={"n_queries": len(vals)},
            ))

    if mrr_values:
        eval_results.append(EvalResult(
            suite="known_items",
            metric="mrr",
            value=sum(mrr_values) / len(mrr_values),
            config={"n_queries": len(mrr_values)},
            details=details,
        ))

    return eval_results


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


def log_results(db: Database, results: list[EvalResult]):
    """Log evaluation results to the database."""
    for r in results:
        db.log_eval(
            suite=r.suite,
            metric=r.metric,
            value=r.value,
            stdev=r.stdev,
            config=r.config,
        )
    logger.info("Logged %d eval results", len(results))
