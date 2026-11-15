"""Eval results and logging them to the ``eval_runs`` table."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kinolog.store import Database

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    suite: str
    metric: str
    value: float
    stdev: float | None = None
    config: dict | None = None
    details: list[dict] | None = None


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
