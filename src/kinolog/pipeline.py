"""Ingest pipeline steps as plain functions.

Each step is idempotent and returns its stats dict. The CLI wraps them with argument parsing and
printing; the web import route calls ``load_letterboxd``.
"""

from __future__ import annotations

from pathlib import Path

from kinolog.config import DEFAULT_MODEL, DEFAULT_STRATEGY
from kinolog.store import Database


def load_letterboxd(db: Database, path: str | Path) -> dict:
    from kinolog.sources.letterboxd.load import load_letterboxd as load

    return load(db, path)


def load_goodreads(db: Database, path: str | Path) -> dict:
    from kinolog.sources.goodreads.load import load_goodreads as load

    return load(db, path)


def resolve(db: Database, item_type: str = "film") -> dict:
    """Match unresolved items to TMDB (needs TMDB_API_KEY)."""
    from kinolog.sources.tmdb.resolve import TMDBResolver

    resolver = TMDBResolver()
    stats = resolver.resolve_all(db, item_type=item_type)
    resolver.close()
    return stats


def enrich(db: Database, item_type: str = "film") -> dict:
    """Fetch TMDB details and build documents for resolved items."""
    from kinolog.sources.tmdb.client import TMDBClient
    from kinolog.sources.tmdb.enrich import enrich_all

    client = TMDBClient()
    stats = enrich_all(db, client, item_type=item_type)
    client.close()
    return stats


def backfill_runtime(db: Database) -> dict:
    """Set runtime_min / is_tv from stored TMDB documents (no network)."""
    from kinolog.sources.tmdb.enrich import backfill_runtime_and_tv

    return backfill_runtime_and_tv(db)


def chunk(
    db: Database, strategy: str = DEFAULT_STRATEGY, item_type: str | None = None
) -> dict:
    from kinolog.index.chunking import chunk_all_documents

    return chunk_all_documents(db, strategy=strategy, item_type=item_type)


def embed(
    db: Database,
    model: str = DEFAULT_MODEL,
    strategy: str = DEFAULT_STRATEGY,
    device: str | None = None,
) -> dict:
    """Embed chunks of one strategy. Raises ValueError for an unknown model name."""
    from kinolog.index.embedding import BGE_M3, MultilingualE5, embed_chunks

    if model == "bge_m3":
        embed_model = BGE_M3(device=device)
    elif model == "multilingual_e5":
        embed_model = MultilingualE5(device=device)
    else:
        raise ValueError(f"Unknown model: {model}")
    return embed_chunks(db, embed_model, strategy=strategy)
