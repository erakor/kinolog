"""Faithfulness evaluation: measure % fully grounded answers across benchmark questions."""

from __future__ import annotations

import json
import logging
from importlib import resources
from pathlib import Path
from typing import Callable

from kinolog.eval.runner import EvalResult
from kinolog.rag.agent import KinologChatAgent
from kinolog.store import Database

logger = logging.getLogger(__name__)

PROMPTS_PATH = Path(str(resources.files("kinolog.eval") / "datasets" / "faithfulness_prompts.json"))


def load_faithfulness_prompts(path: Path = PROMPTS_PATH) -> list[dict]:
    if not path.exists():
        logger.warning("Faithfulness prompts file not found: %s", path)
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def eval_faithfulness(
    db: Database,
    agent: KinologChatAgent | None = None,
    prompts: list[dict] | None = None,
    generator_fn: Callable[[str, str], str] | None = None,
) -> list[EvalResult]:
    """
    Run the faithfulness evaluation suite across fixed chat prompts.
    Metric: % fully grounded answers (where all named films appear in retrieved context).
    """
    if prompts is None:
        prompts = load_faithfulness_prompts()
    if not prompts:
        return []

    if agent is None:
        agent = KinologChatAgent(db)

    grounded_scores = []
    fully_grounded_count = 0
    details = []

    for p in prompts:
        q = p["question"]
        res = agent.answer_query(q, generator_fn=generator_fn)
        score = res["groundedness"]
        is_fully = res["is_fully_grounded"]

        grounded_scores.append(score)
        if is_fully:
            fully_grounded_count += 1

        details.append({
            "id": p.get("id"),
            "question": q,
            "groundedness": score,
            "is_fully_grounded": is_fully,
            "mentioned": res["mentioned_item_ids"],
            "context": res["context_item_ids"],
        })

    pct_fully_grounded = (fully_grounded_count / len(prompts)) * 100.0
    mean_groundedness = sum(grounded_scores) / len(grounded_scores)

    return [
        EvalResult(
            suite="faithfulness",
            metric="pct_fully_grounded",
            value=pct_fully_grounded,
            config={"n_prompts": len(prompts)},
            details=details,
        ),
        EvalResult(
            suite="faithfulness",
            metric="mean_groundedness",
            value=mean_groundedness,
            config={"n_prompts": len(prompts)},
        ),
    ]
