"""CLI handlers for the ``ingest`` subcommands (thin wrappers over ``kinolog.pipeline``)."""

from __future__ import annotations

from kinolog import pipeline
from kinolog.config import DEFAULT_MODEL, DEFAULT_STRATEGY
from kinolog.interfaces.cli.output import print_table
from kinolog.store import Database

# --- Core command handlers ---

def handle_ingest_letterboxd(db_path: str, export_dir: str):
    db = Database(db_path)
    stats = pipeline.load_letterboxd(db, export_dir)
    rows = [[k, str(v)] for k, v in stats.items()]
    print_table("Letterboxd Import", ["Metric", "Count"], rows)
    db.close()


def handle_ingest_goodreads(db_path: str, csv_path: str):
    db = Database(db_path)
    stats = pipeline.load_goodreads(db, csv_path)
    rows = [[k, str(v)] for k, v in stats.items()]
    print_table("Goodreads Import", ["Metric", "Count"], rows)
    db.close()


def handle_ingest_resolve(db_path: str, item_type: str = "film"):
    db = Database(db_path)
    stats = pipeline.resolve(db, item_type=item_type)
    rows = [[k, str(v)] for k, v in stats.items()]
    print_table("TMDB Resolution", ["Metric", "Count"], rows)
    db.close()


def handle_ingest_enrich(db_path: str, item_type: str = "film"):
    db = Database(db_path)
    stats = pipeline.enrich(db, item_type=item_type)
    rows = [[k, str(v)] for k, v in stats.items()]
    print_table("TMDB Enrichment", ["Metric", "Count"], rows)
    db.close()


def handle_ingest_backfill_runtime(db_path: str):
    db = Database(db_path)
    stats = pipeline.backfill_runtime(db)
    print_table("Runtime backfill", ["Metric", "Count"], [[k, str(v)] for k, v in stats.items()])
    db.close()


def handle_ingest_review(db_path: str):
    from kinolog.interfaces.cli.review import review_queue
    review_queue(db_path)


def handle_ingest_chunk(
    db_path: str, strategy: str = DEFAULT_STRATEGY, item_type: str | None = None
):
    db = Database(db_path)
    stats = pipeline.chunk(db, strategy=strategy, item_type=item_type)
    print(f"Chunked {stats['total']} documents -> {stats['chunks_created']} chunks")
    db.close()


def handle_ingest_embed(
    db_path: str,
    model: str = DEFAULT_MODEL,
    strategy: str = DEFAULT_STRATEGY,
    device: str | None = None,
):
    db = Database(db_path)
    try:
        stats = pipeline.embed(db, model=model, strategy=strategy, device=device)
    except ValueError as e:
        print(e)
        return
    print(f"Embedded {stats['embedded']}/{stats['total']} chunks")
    db.close()
