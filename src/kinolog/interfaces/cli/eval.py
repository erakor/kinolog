"""CLI handlers for the ``eval`` subcommands."""

from __future__ import annotations

from kinolog.config import DEFAULT_RANKER
from kinolog.interfaces.cli.output import print_table
from kinolog.store import Database


def handle_eval_known_items(db_path: str, mode: str = "bm25"):
    from kinolog.eval.runner import log_results
    from kinolog.eval.suites.known_items import eval_known_items
    from kinolog.retrieval import search as do_search
    db = Database(db_path)
    model = None
    if mode in ("vector", "rrf"):
        from kinolog.index.embedding import BGE_M3
        model = BGE_M3()

    def search_fn(query):
        return do_search(db, query, model=model, mode=mode, limit=20)

    results = eval_known_items(db, search_fn)
    log_results(db, results)
    rows = [[r.metric, f"{r.value:.4f}"] for r in results]
    print_table(f"Known-Item Eval ({mode})", ["Metric", "Value"], rows)
    db.close()


def handle_eval_hearts(db_path: str, ranker: str = "mean_heart", splits: int = 10):
    from kinolog.eval.runner import log_results
    from kinolog.eval.suites.hearts import eval_hearts_recall
    from kinolog.taste import RANKERS
    db = Database(db_path)
    if ranker not in RANKERS:
        print(f"Unknown ranker: {ranker}. Available: {list(RANKERS.keys())}")
        return
    rank_fn = RANKERS[ranker]
    results = eval_hearts_recall(db, rank_fn, n_splits=splits)
    log_results(db, results)
    rows = [[r.metric, f"{r.value:.4f}", f"{r.stdev:.4f}" if r.stdev else "—"] for r in results]
    print_table(f"Hearts Recall — {ranker}", ["Metric", "Mean", "Stdev"], rows)
    db.close()


def handle_eval_concierge(
    db_path: str, mode: str = "bm25", ranker: str = DEFAULT_RANKER,
    w_taste: float = 0.0, w_comp: float = 0.0, hearts: bool = False, splits: int = 5,
):
    from kinolog.eval.runner import log_results
    from kinolog.eval.suites.concierge import eval_concierge, eval_concierge_hearts
    from kinolog.taste import RANKERS, taste_scores
    db = Database(db_path)
    if ranker not in RANKERS:
        print(f"Unknown ranker: {ranker}. Available: {list(RANKERS.keys())}")
        return
    model = None
    if mode in ("vector", "rrf"):
        from kinolog.index.embedding import BGE_M3
        model = BGE_M3()

    def taste_fn(ids):
        return taste_scores(db, ids, ranker)

    results = eval_concierge(
        db, model=model, taste_fn=taste_fn if w_taste else None, w_taste=w_taste, w_comp=w_comp,
        config={"mode": mode, "ranker": ranker},
    )
    if hearts:
        results += eval_concierge_hearts(
            db, RANKERS[ranker], model=model, w_taste=w_taste or 0.5, n_splits=splits
        )
    log_results(db, results)
    rows = [[r.metric, f"{r.value:.4f}", f"{r.stdev:.4f}" if r.stdev else "—"] for r in results]
    print_table(f"Concierge Eval ({mode}, {ranker})", ["Metric", "Value", "Stdev"], rows)
    db.close()
