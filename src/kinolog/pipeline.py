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


def filmographies(
    db: Database,
    min_seen: int = 2,
    person_name: str | None = None,
    limit: int | None = None,
    fetch_details: bool = True,
    refresh: bool = False,
) -> dict:
    """Fetch full TMDB director filmographies (needs TMDB_API_KEY).

    Covers directors with at least ``min_seen`` seen films, or those matching ``person_name``.
    """
    from kinolog.sources.tmdb.client import TMDBClient
    from kinolog.sources.tmdb.filmography import enrich_all_filmographies

    client = TMDBClient()
    try:
        return enrich_all_filmographies(
            db, client, min_seen=min_seen, person_name=person_name, limit=limit,
            fetch_details=fetch_details, refresh=refresh,
        )
    finally:
        client.close()


def omdb(
    db: Database,
    item_type: str = "film",
    max_requests: int | None = None,
    refresh: bool = False,
) -> dict:
    """Fetch IMDb / Rotten Tomatoes / Metacritic scores from OMDb (needs OMDB_API_KEY).

    Raises ValueError when the key is missing.
    """
    from kinolog.sources.omdb.client import DAILY_LIMIT, OMDbClient
    from kinolog.sources.omdb.enrich import enrich_all

    client = OMDbClient()
    try:
        return enrich_all(
            db, client, item_type=item_type, refresh=refresh,
            max_requests=DAILY_LIMIT if max_requests is None else max_requests,
        )
    finally:
        client.close()


def backfill_runtime(db: Database) -> dict:
    """Set runtime_min / is_tv / imdb_id from stored TMDB documents and cache (no network)."""
    from kinolog.sources.tmdb.enrich import backfill_imdb_ids, backfill_runtime_and_tv

    return {**backfill_runtime_and_tv(db), **{
        f"cache_{k}": v for k, v in backfill_imdb_ids(db).items()
    }}


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
    from kinolog.index.embedding import EMBEDDERS, embed_chunks

    if model not in EMBEDDERS:
        raise ValueError(f"Unknown model: {model}")
    return embed_chunks(db, EMBEDDERS[model](device=device), strategy=strategy)
