"""Known-item retrieval: Hit@k and MRR over a fixed query set."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from importlib import resources
from pathlib import Path

from kinolog.eval.metrics import hit_at_k, mrr
from kinolog.eval.runner import EvalResult
from kinolog.store import Database

logger = logging.getLogger(__name__)


# --- Known-item eval ---


KNOWN_ITEMS_PATH = Path(str(resources.files("kinolog.eval") / "datasets" / "known_items.json"))


def load_known_item_queries(path: str | Path = KNOWN_ITEMS_PATH) -> list[dict]:
    """Load known-item queries from JSON file."""
    p = Path(path)
    if not p.exists():
        logger.warning("Known-item query file not found: %s", path)
        return []
    with open(p, encoding="utf-8") as f:
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

        details.append(
            {
                "query": query_text,
                "target": target_title,
                "hit_5": hit_at_k(result_ids, target_id, 5),
                "mrr": mrr_val,
                "rank": result_ids.index(target_id) + 1 if target_id in result_ids else None,
            }
        )

    eval_results = []
    for k in k_values:
        vals = results_by_k[k]
        if vals:
            eval_results.append(
                EvalResult(
                    suite="known_items",
                    metric=f"hit@{k}",
                    value=sum(vals) / len(vals),
                    config={"n_queries": len(vals)},
                )
            )

    if mrr_values:
        eval_results.append(
            EvalResult(
                suite="known_items",
                metric="mrr",
                value=sum(mrr_values) / len(mrr_values),
                config={"n_queries": len(mrr_values)},
                details=details,
            )
        )

    return eval_results
