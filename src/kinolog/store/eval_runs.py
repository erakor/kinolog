"""Evaluation run log."""

from __future__ import annotations

import json


class EvalRunsMixin:
    def log_eval(
        self,
        suite: str,
        metric: str,
        value: float,
        stdev: float | None = None,
        config: dict | None = None,
    ):
        """Log an evaluation run."""
        from datetime import datetime, timezone

        self.conn.execute(
            "INSERT INTO eval_runs (run_at, suite, config_json, metric, value, stdev) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                suite,
                json.dumps(config) if config else None,
                metric,
                value,
                stdev,
            ),
        )
        self.conn.commit()
