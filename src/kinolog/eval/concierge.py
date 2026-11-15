"""Concierge evaluation: parser accuracy, constraint satisfaction, retrieval quality,
rationale faithfulness, and a held-out-hearts check for the taste rerank weight.

Run with ``python3 -m kinolog.interfaces.cli eval concierge``; results are written to ``eval_runs``
through ``harness.log_results`` with suite="concierge".
"""

from __future__ import annotations

import json
import logging
import random
import re
import statistics
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

from kinolog.eval.harness import EvalResult
from kinolog.eval.metrics import hit_at_k, mrr, ndcg_at_k
from kinolog.features.concierge import parse_constraints, pick, to_search_filters
from kinolog.store import Database

logger = logging.getLogger(__name__)

PROMPTS_PATH = Path(str(resources.files("kinolog.eval") / "datasets" / "concierge_prompts.json"))
CONSTRAINT_FIELDS = (
    "runtime_max", "runtime_min", "decade", "year_min", "year_max", "seen", "on_watchlist",
)
CITE_RE = re.compile(r"\[\^(\d+)\]")


def load_concierge_prompts(path: Path = PROMPTS_PATH) -> list[dict]:
    if not Path(path).exists():
        logger.warning("Concierge prompt file not found: %s", path)
        return []
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _find_item(db: Database, title: str, year: int | None) -> int | None:
    row = db.execute(
        "SELECT id FROM items WHERE title = ? AND year IS ? AND item_type = 'film'", (title, year)
    ).fetchone()
    return row["id"] if row else None


def violates(card: dict, f) -> list[str]:
    """Hard-constraint violations of an item card against SearchFilters (empty = satisfied)."""
    bad = []
    rt, year, st = card.get("runtime_min"), card.get("year"), card["status"]
    if (f.runtime_max is not None or f.runtime_min is not None) and rt is None:
        bad.append("runtime_unknown")
    if f.runtime_max is not None and rt is not None and rt > f.runtime_max:
        bad.append("runtime_max")
    if f.runtime_min is not None and rt is not None and rt < f.runtime_min:
        bad.append("runtime_min")
    if f.decade and not (year and f.decade <= year < f.decade + 10):
        bad.append("decade")
    if f.year_min and not (year and year >= f.year_min):
        bad.append("year_min")
    if f.year_max and not (year and year <= f.year_max):
        bad.append("year_max")
    if f.seen is not None and st["seen"] != f.seen:
        bad.append("seen")
    if f.on_watchlist is not None and st["on_watchlist"] != f.on_watchlist:
        bad.append("on_watchlist")
    return bad


def eval_concierge(
    db: Database,
    *,
    prompts: list[dict] | None = None,
    model: Any = None,
    scope: str = "all",
    limit: int = 5,
    taste_fn: Callable[[list[int]], dict[int, float]] | None = None,
    w_taste: float = 0.0,
    w_comp: float = 0.0,
    generator_fn: Callable[[str, str], str] | None = None,
    config: dict | None = None,
) -> list[EvalResult]:
    prompts = load_concierge_prompts() if prompts is None else prompts
    if not prompts:
        return []
    cfg = {"scope": scope, "limit": limit, "w_taste": w_taste, "w_comp": w_comp,
           "generator": "llm" if generator_fn else "template", **(config or {})}

    exact, field_hits, field_total = [], 0, 0
    satisfied, picked = 0, 0
    hit = {1: [], 3: [], 5: []}
    rr, ndcg = [], []
    ground, cite_ok, cite_total, fallbacks, with_gen = [], 0, 0, 0, 0

    for p in prompts:
        parsed = parse_constraints(p["query"])
        expected = p.get("expected_filters", {})
        ok = True
        for fld in CONSTRAINT_FIELDS:
            match = parsed.filters.get(fld) == expected.get(fld)
            field_hits += match
            field_total += 1
            ok = ok and match
        exact.append(1.0 if ok else 0.0)

        out = pick(
            db, p["query"], model=model, scope=scope, limit=limit, generator_fn=generator_fn,
            taste_fn=taste_fn, w_taste=w_taste, w_comp=w_comp,
        )
        sf = to_search_filters(parsed, scope)
        ids = [pk["item"]["item_id"] for pk in out["picks"]]
        for pk in out["picks"]:
            picked += 1
            satisfied += 0 if violates(pk["item"], sf) else 1
            r = pk["rationale"]
            ground.append(r["groundedness"])
            valid = {c["n"] for c in r["citations"]}
            nums = [int(n) for n in CITE_RE.findall(r["text"])]
            cite_total += len(nums)
            cite_ok += sum(1 for n in nums if n in valid)
        if generator_fn is not None and out["picks"]:
            with_gen += 1
            fallbacks += any(d.startswith("llm_ungrounded") for d in out["degraded"])

        rel = {_find_item(db, r["title"], r.get("year")) for r in p.get("relevant", [])} - {None}
        acc = {_find_item(db, r["title"], r.get("year")) for r in p.get("acceptable", [])} - {None}
        if rel:
            for k in hit:
                hit[k].append(float(any(hit_at_k(ids, t, k) for t in rel)))
            rr.append(mrr(ids, rel))
            gains = {i: 1.0 for i in rel} | {i: 0.5 for i in acc if i not in rel}
            ndcg.append(ndcg_at_k(ids, gains, 5))

    def res(metric: str, values: list[float] | float, **kw) -> EvalResult:
        v = statistics.mean(values) if isinstance(values, list) else values
        return EvalResult(suite="concierge", metric=metric, value=float(v), config=cfg, **kw)

    results = [
        res("parser_exact_match", exact),
        res("parser_field_accuracy", field_hits / field_total if field_total else 0.0),
        res("constraint_satisfaction", satisfied / picked if picked else 1.0),
    ]
    for k, vals in hit.items():
        if vals:
            results.append(res(f"hit@{k}", vals))
    if rr:
        results += [res("mrr", rr), res("ndcg@5", ndcg)]
    if ground:
        results += [
            res("rationale_groundedness", ground),
            res("citation_validity", cite_ok / cite_total if cite_total else 1.0),
        ]
    if with_gen:
        results.append(res("llm_fallback_rate", fallbacks / with_gen))
    return results


def _heart_prompt(db: Database, item_id: int) -> str | None:
    from kinolog.features.docfacts import item_facts

    genres = item_facts(db, [item_id])[item_id]["genres"]
    return f"a {genres[0].lower()} film" if genres else None


def eval_concierge_hearts(
    db: Database,
    taste_ranker: Callable[..., list],
    *,
    model: Any = None,
    w_taste: float = 0.5,
    n_splits: int = 5,
    holdout_frac: float = 0.2,
    k_values: tuple[int, ...] = (5, 10),
    seed: int = 0,
    max_per_split: int = 25,
) -> list[EvalResult]:
    """Does the taste weight surface held-out hearts? (Positive-Unlabeled style.)

    Each split hides a fraction of hearts, trains the ranker on the rest (removed from the
    candidates), and asks genre prompts derived from each hidden heart. Hit@k is whether the
    hidden heart appears in the top-k picks. Compare w_taste=0 against w_taste>0.
    """
    hearts = db.get_heart_ids()
    if len(hearts) < 5:
        logger.warning("Too few hearts (%d) for the concierge hearts check", len(hearts))
        return []
    rng = random.Random(seed)
    per_k: dict[int, list[float]] = {k: [] for k in k_values}
    for _ in range(n_splits):
        shuffled = hearts[:]
        rng.shuffle(shuffled)
        n_hold = max(1, int(len(shuffled) * holdout_frac))
        held, train = shuffled[:n_hold][:max_per_split], shuffled[n_hold:]

        def taste_fn(ids: list[int], train=train) -> dict[int, float]:
            return {s.item_id: s.score for s in taste_ranker(db, ids, train)}

        hits = {k: [] for k in k_values}
        for h in held:
            prompt = _heart_prompt(db, h)
            if not prompt:
                continue
            out = pick(
                db, prompt, model=model, scope="all", limit=max(k_values), exclude_ids=train,
                taste_fn=taste_fn, w_taste=w_taste, rationales=False,
            )
            ids = [pk["item"]["item_id"] for pk in out["picks"]]
            for k in k_values:
                hits[k].append(float(h in ids[:k]))
        for k in k_values:
            if hits[k]:
                per_k[k].append(statistics.mean(hits[k]))
    cfg = {"w_taste": w_taste, "splits": n_splits, "holdout_frac": holdout_frac}
    return [
        EvalResult(
            suite="concierge", metric=f"hearts_hit@{k}", value=statistics.mean(v),
            stdev=statistics.stdev(v) if len(v) > 1 else 0.0, config=cfg,
        )
        for k, v in per_k.items() if v
    ]
