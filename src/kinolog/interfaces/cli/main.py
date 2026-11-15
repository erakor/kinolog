"""Argument parsing and command dispatch."""

from __future__ import annotations

import argparse
import logging

from kinolog.config import DEFAULT_DB_PATH, DEFAULT_MODEL, DEFAULT_RANKER, DEFAULT_STRATEGY
from kinolog.interfaces.cli.eval import (
    handle_eval_concierge,
    handle_eval_hearts,
    handle_eval_known_items,
)
from kinolog.interfaces.cli.ingest import (
    handle_ingest_backfill_runtime,
    handle_ingest_chunk,
    handle_ingest_embed,
    handle_ingest_enrich,
    handle_ingest_filmographies,
    handle_ingest_goodreads,
    handle_ingest_letterboxd,
    handle_ingest_omdb,
    handle_ingest_resolve,
    handle_ingest_review,
)
from kinolog.interfaces.cli.query import (
    handle_crew_overlap,
    handle_filmography,
    handle_search,
    handle_stats,
)


def build_parser() -> argparse.ArgumentParser:
    """The full argument parser (every subcommand accepts --db and -v)."""
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

    omdb_parser = ingest_subs.add_parser(
        "omdb", help="Fetch IMDb/Rotten Tomatoes/Metacritic scores from OMDb",
        parents=[base_parser],
    )
    omdb_parser.add_argument("--type", default="film", help="Item type")
    omdb_parser.add_argument("--max-requests", type=int, default=None,
                             help="Cap on network requests this run (free tier: 1000/day)")
    omdb_parser.add_argument("--refresh", action="store_true",
                             help="Re-fetch cached responses (counts against the cap)")

    film_ing = ingest_subs.add_parser(
        "filmographies",
        help="Fetch full TMDB director filmographies (for completion beyond the index)",
        parents=[base_parser],
    )
    film_ing.add_argument("--min-seen", type=int, default=2,
                          help="Only directors with at least this many seen films")
    film_ing.add_argument("--person", default=None, help="Only people whose name matches")
    film_ing.add_argument("--limit", type=int, default=None, help="Cap on directors this run")
    film_ing.add_argument("--no-details", action="store_true",
                          help="Skip per-film detail requests (films not already cached are "
                               "not counted until details are fetched)")
    film_ing.add_argument("--refresh", action="store_true",
                          help="Re-fetch cached person credits (filmographies grow)")

    ingest_subs.add_parser(
        "backfill-runtime",
        help="Set runtime/TV flag/IMDb id from stored TMDB documents and cache (no network)",
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
    return parser


def run_argparse_cli():
    args = build_parser().parse_args()

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
        elif args.ingest_cmd == "omdb":
            handle_ingest_omdb(args.db, args.type, args.max_requests, args.refresh)
        elif args.ingest_cmd == "filmographies":
            handle_ingest_filmographies(
                args.db, args.min_seen, args.person, args.limit, not args.no_details, args.refresh
            )
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
