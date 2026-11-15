"""Kinolog CLI — film & book index."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from kinolog.config import DEFAULT_DB_PATH, DEFAULT_MODEL, DEFAULT_RANKER, DEFAULT_STRATEGY
from kinolog.store import Database

logger = logging.getLogger(__name__)

try:
    import click
    from rich.console import Console
    from rich.table import Table
    USE_CLICK = True
    console = Console()
except ImportError:
    USE_CLICK = False
    console = None


def print_table(title: str, headers: list[str], rows: list[list[str]]):
    """Render a table with Rich if available, else plain ASCII."""
    if USE_CLICK and console:
        tbl = Table(title=title)
        for h in headers:
            tbl.add_column(h)
        for r in rows:
            tbl.add_row(*[str(x) for x in r])
        console.print(tbl)
    else:
        if not rows:
            print(f"\n=== {title} === (empty)\n")
            return
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, val in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(val)))
        sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
        print(f"\n=== {title} ===")
        print(sep)
        header_line = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
        print(header_line)
        print(sep)
        for row in rows:
            line = "| " + " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)) + " |"
            print(line)
        print(sep + "\n")


# --- Core command handlers ---

def handle_ingest_letterboxd(db_path: str, export_dir: str):
    from kinolog.ingest.letterboxd import load_letterboxd
    db = Database(db_path)
    stats = load_letterboxd(db, export_dir)
    rows = [[k, str(v)] for k, v in stats.items()]
    print_table("Letterboxd Import", ["Metric", "Count"], rows)
    db.close()


def handle_ingest_goodreads(db_path: str, csv_path: str):
    from kinolog.ingest.goodreads import load_goodreads
    db = Database(db_path)
    stats = load_goodreads(db, csv_path)
    rows = [[k, str(v)] for k, v in stats.items()]
    print_table("Goodreads Import", ["Metric", "Count"], rows)
    db.close()


def handle_ingest_resolve(db_path: str, item_type: str = "film"):
    from kinolog.ingest.resolvers.tmdb import TMDBResolver
    db = Database(db_path)
    resolver = TMDBResolver()
    stats = resolver.resolve_all(db, item_type=item_type)
    rows = [[k, str(v)] for k, v in stats.items()]
    print_table("TMDB Resolution", ["Metric", "Count"], rows)
    resolver.close()
    db.close()


def handle_ingest_enrich(db_path: str, item_type: str = "film"):
    from kinolog.ingest.enrichers.tmdb import enrich_all
    from kinolog.ingest.resolvers.tmdb import TMDBResolver
    db = Database(db_path)
    resolver = TMDBResolver()
    stats = enrich_all(db, resolver, item_type=item_type)
    rows = [[k, str(v)] for k, v in stats.items()]
    print_table("TMDB Enrichment", ["Metric", "Count"], rows)
    resolver.close()
    db.close()


def handle_ingest_backfill_runtime(db_path: str):
    from kinolog.ingest.enrichers.tmdb import backfill_runtime_and_tv
    db = Database(db_path)
    stats = backfill_runtime_and_tv(db)
    print_table("Runtime backfill", ["Metric", "Count"], [[k, str(v)] for k, v in stats.items()])
    db.close()


def handle_ingest_review(db_path: str):
    from kinolog.ingest.review_cli import review_queue
    review_queue(db_path)


def handle_ingest_chunk(
    db_path: str, strategy: str = DEFAULT_STRATEGY, item_type: str | None = None
):
    from kinolog.core.chunkers import chunk_all_documents
    db = Database(db_path)
    stats = chunk_all_documents(db, strategy=strategy, item_type=item_type)
    print(f"Chunked {stats['total']} documents -> {stats['chunks_created']} chunks")
    db.close()


def handle_ingest_embed(db_path: str, model: str = DEFAULT_MODEL, strategy: str = DEFAULT_STRATEGY, device: str | None = None):
    from kinolog.core.embed import BGE_M3, MultilingualE5, embed_chunks
    db = Database(db_path)
    if model == "bge_m3":
        embed_model = BGE_M3(device=device)
    elif model == "multilingual_e5":
        embed_model = MultilingualE5(device=device)
    else:
        print(f"Unknown model: {model}")
        return
    stats = embed_chunks(db, embed_model, strategy=strategy)
    print(f"Embedded {stats['embedded']}/{stats['total']} chunks")
    db.close()


def handle_search(db_path: str, query: str, mode: str = "bm25", limit: int = 10,
                  item_type: str | None = None, seen: bool | None = None):
    from kinolog.core.search import SearchFilters, search as do_search
    db = Database(db_path)
    filters = SearchFilters(item_type=item_type, seen=seen)
    model = None
    if mode in ("vector", "rrf"):
        try:
            from kinolog.core.embed import BGE_M3
            model = BGE_M3()
        except Exception as e:
            print(f"Vector model not available ({e}), falling back to BM25")
            mode = "bm25"
    results = do_search(db, query, model=model, mode=mode, limit=limit, filters=filters)
    rows = [[str(i + 1), r.title, str(r.year or ""), f"{r.score:.4f}", r.source]
            for i, r in enumerate(results)]
    print_table(f"Search: {query} ({mode})", ["#", "Title", "Year", "Score", "Source"], rows)
    db.close()


def handle_stats(db_path: str):
    db = Database(db_path)
    s = db.stats()
    queue = db.get_review_queue()
    matched = db.execute("SELECT COUNT(*) as c FROM items WHERE tmdb_id IS NOT NULL").fetchone()
    rows = [[k, str(v)] for k, v in s.items()]
    rows.append(["review_queue", str(len(queue))])
    rows.append(["items_matched", str(matched["c"])])
    print_table("Database Stats", ["Table", "Rows"], rows)
    db.close()


def handle_filmography(db_path: str, name: str, role: str | None = None):
    from kinolog.core.crew import filmography as get_filmography
    db = Database(db_path)
    entries = get_filmography(db, person_name=name, role=role)
    for entry in entries:
        print(f"\n{entry.person_name} — {entry.role}")
        print(f"  Seen {entry.total_seen}/{entry.total_in_db} in database")
        rows = [[str(f.get("year", "")), f["title"], "✓" if f["seen"] else ""] for f in entry.films]
        print_table(f"Filmography: {entry.person_name}", ["Year", "Title", "Seen"], rows)
    db.close()


def handle_crew_overlap(db_path: str, role: str = "Director", min_overlap: int = 2):
    from kinolog.core.crew import crew_overlap_with_hearts
    db = Database(db_path)
    results = crew_overlap_with_hearts(db, role=role, min_overlap=min_overlap)
    rows = []
    for r in results:
        films_str = ", ".join(f["title"] for f in r.films[:5])
        if len(r.films) > 5:
            films_str += f" (+{len(r.films) - 5})"
        rows.append([r.person_name, str(r.overlap_count), str(r.total_seen), films_str])
    print_table(f"Crew Overlap — {role}s in hearted films", ["Name", "Hearts", "Seen", "Films"], rows)
    db.close()


def handle_eval_known_items(db_path: str, mode: str = "bm25"):
    from kinolog.core.search import search as do_search
    from kinolog.eval.harness import eval_known_items, log_results
    db = Database(db_path)
    model = None
    if mode in ("vector", "rrf"):
        from kinolog.core.embed import BGE_M3
        model = BGE_M3()

    def search_fn(query):
        return do_search(db, query, model=model, mode=mode, limit=20)

    results = eval_known_items(db, search_fn)
    log_results(db, results)
    rows = [[r.metric, f"{r.value:.4f}"] for r in results]
    print_table(f"Known-Item Eval ({mode})", ["Metric", "Value"], rows)
    db.close()


def handle_eval_hearts(db_path: str, ranker: str = "mean_heart", splits: int = 10):
    from kinolog.core.taste import RANKERS
    from kinolog.eval.harness import eval_hearts_recall, log_results
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
    from kinolog.core.taste import RANKERS, taste_scores
    from kinolog.eval.concierge import eval_concierge, eval_concierge_hearts
    from kinolog.eval.harness import log_results
    db = Database(db_path)
    if ranker not in RANKERS:
        print(f"Unknown ranker: {ranker}. Available: {list(RANKERS.keys())}")
        return
    model = None
    if mode in ("vector", "rrf"):
        from kinolog.core.embed import BGE_M3
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


# --- Argparse CLI (universal, zero external dependency) ---

def run_argparse_cli():
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument(
        "--db", default=str(DEFAULT_DB_PATH), help="Path to SQLite index database"
    )
    base_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    parser = argparse.ArgumentParser(prog="kinolog", description="Personal Film & Book Index", parents=[base_parser])
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest
    ingest_parser = subparsers.add_parser("ingest", help="Ingestion commands", parents=[base_parser])
    ingest_subs = ingest_parser.add_subparsers(dest="ingest_cmd", required=True)

    lb_parser = ingest_subs.add_parser("letterboxd", help="Load Letterboxd export CSVs", parents=[base_parser])
    lb_parser.add_argument("export_dir", help="Path to directory containing Letterboxd CSVs or zip")

    gr_parser = ingest_subs.add_parser("goodreads", help="Load Goodreads export CSV", parents=[base_parser])
    gr_parser.add_argument("csv_path", help="Path to Goodreads CSV file")

    res_parser = ingest_subs.add_parser("resolve", help="Resolve items to TMDB IDs", parents=[base_parser])
    res_parser.add_argument("--type", default="film", help="Item type (film/book)")

    enr_parser = ingest_subs.add_parser("enrich", help="Enrich items with TMDB metadata", parents=[base_parser])
    enr_parser.add_argument("--type", default="film", help="Item type (film/book)")

    ingest_subs.add_parser(
        "backfill-runtime", help="Set runtime/TV flag from existing TMDB documents",
        parents=[base_parser],
    )

    ingest_subs.add_parser("review", help="Review and clear the match review queue", parents=[base_parser])

    chk_parser = ingest_subs.add_parser("chunk", help="Chunk documents", parents=[base_parser])
    chk_parser.add_argument("--strategy", default=DEFAULT_STRATEGY, help="Chunk strategy")
    chk_parser.add_argument("--type", default=None, help="Item type filter")

    emb_parser = ingest_subs.add_parser("embed", help="Embed chunks", parents=[base_parser])
    emb_parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    emb_parser.add_argument("--strategy", default=DEFAULT_STRATEGY, help="Chunk strategy")
    emb_parser.add_argument("--device", default=None, help="Device (cpu/mps/cuda)")

    # Search
    search_parser = subparsers.add_parser("search", help="Search the index", parents=[base_parser])
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--mode", default="bm25", choices=["bm25", "vector", "rrf"])
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument("--type", default=None, help="Filter by item type")
    search_parser.add_argument("--seen", type=bool, default=None, help="Filter by seen status")

    # Stats
    subparsers.add_parser("stats", help="Show database statistics", parents=[base_parser])

    # Filmography
    film_parser = subparsers.add_parser("filmography", help="Show person's filmography", parents=[base_parser])
    film_parser.add_argument("name", help="Person name")
    film_parser.add_argument("--role", default=None, help="Filter by role")

    # Crew overlap
    crew_parser = subparsers.add_parser("crew-overlap", help="Find crew in hearted films", parents=[base_parser])
    crew_parser.add_argument("--role", default="Director", help="Role")
    crew_parser.add_argument("--min-overlap", type=int, default=2)

    # Eval
    eval_parser = subparsers.add_parser("eval", help="Evaluation commands", parents=[base_parser])
    eval_subs = eval_parser.add_subparsers(dest="eval_cmd", required=True)

    ki_parser = eval_subs.add_parser("known-items", help="Run known-item retrieval eval", parents=[base_parser])
    ki_parser.add_argument("--mode", default="bm25", choices=["bm25", "vector", "rrf"])

    con_parser = eval_subs.add_parser("concierge", help="Run concierge eval", parents=[base_parser])
    con_parser.add_argument("--mode", default="bm25", choices=["bm25", "rrf"])
    con_parser.add_argument("--ranker", default=DEFAULT_RANKER, help="Taste ranker")
    con_parser.add_argument("--w-taste", type=float, default=0.0)
    con_parser.add_argument("--w-comp", type=float, default=0.0)
    con_parser.add_argument("--hearts", action="store_true", help="Also run held-out hearts check")
    con_parser.add_argument("--splits", type=int, default=5)

    hearts_parser = eval_subs.add_parser("hearts", help="Run hearts recall eval", parents=[base_parser])
    hearts_parser.add_argument("--ranker", default="mean_heart", help="Taste ranker")
    hearts_parser.add_argument("--splits", type=int, default=10)

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "ingest":
        if args.ingest_cmd == "letterboxd":
            handle_ingest_letterboxd(args.db, args.export_dir)
        elif args.ingest_cmd == "goodreads":
            handle_ingest_goodreads(args.db, args.csv_path)
        elif args.ingest_cmd == "resolve":
            handle_ingest_resolve(args.db, args.type)
        elif args.ingest_cmd == "enrich":
            handle_ingest_enrich(args.db, args.type)
        elif args.ingest_cmd == "backfill-runtime":
            handle_ingest_backfill_runtime(args.db)
        elif args.ingest_cmd == "review":
            handle_ingest_review(args.db)
        elif args.ingest_cmd == "chunk":
            handle_ingest_chunk(args.db, args.strategy, args.type)
        elif args.ingest_cmd == "embed":
            handle_ingest_embed(args.db, args.model, args.strategy, args.device)
    elif args.command == "search":
        handle_search(args.db, args.query, mode=args.mode, limit=args.limit,
                      item_type=args.type, seen=args.seen)
    elif args.command == "stats":
        handle_stats(args.db)
    elif args.command == "filmography":
        handle_filmography(args.db, args.name, args.role)
    elif args.command == "crew-overlap":
        handle_crew_overlap(args.db, role=args.role, min_overlap=args.min_overlap)
    elif args.command == "eval":
        if args.eval_cmd == "concierge":
            handle_eval_concierge(args.db, args.mode, args.ranker, args.w_taste, args.w_comp,
                                  args.hearts, args.splits)
        elif args.eval_cmd == "known-items":
            handle_eval_known_items(args.db, mode=args.mode)
        elif args.eval_cmd == "hearts":
            handle_eval_hearts(args.db, ranker=args.ranker, splits=args.splits)


def cli():
    run_argparse_cli()


if __name__ == "__main__":
    cli()
