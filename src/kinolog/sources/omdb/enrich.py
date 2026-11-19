"""OMDb enricher: critic and audience scores keyed by the IMDb id TMDB gives us.

OMDb is only asked for ratings: one request per film returns IMDb, Rotten Tomatoes and Metacritic
scores, normalized to 0..100 and stored in ``external_ratings``. Nothing here is written to
``documents``, so ratings never leak into chunk text or retrieval. The free tier allows 1,000
requests/day: ``max_requests`` caps network calls per run, and a "Request limit reached" answer
stops the batch cleanly."""

from __future__ import annotations

import logging
import re

from kinolog.sources.omdb.client import (
    DAILY_LIMIT,
    MAX_CONSECUTIVE_FAILURES,
    PROVIDER,
    OMDbClient,
    OMDbQuotaError,
    OMDbUnavailableError,
)
from kinolog.store import Database

logger = logging.getLogger(__name__)


# OMDb "Ratings" array source names -> our source keys
_SOURCE_KEYS = {
    "Internet Movie Database": "imdb",
    "Rotten Tomatoes": "rotten_tomatoes",
    "Metacritic": "metacritic",
}


def _parse_score(raw: str) -> float | None:
    """'8.1/10' -> 81.0, '94%' -> 94.0, '73/100' -> 73.0; None for 'N/A' or junk."""
    raw = (raw or "").strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*%", raw)
    if m:
        return float(m.group(1))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", raw)
    if m and float(m.group(2)) > 0:
        return round(float(m.group(1)) * 100.0 / float(m.group(2)), 1)
    return None


def _parse_votes(raw: str | None) -> int | None:
    digits = re.sub(r"[,\s]", "", raw or "")
    return int(digits) if digits.isdigit() else None


def parse_ratings(data: dict) -> list[dict]:
    """Normalized ratings from an OMDb title response.

    Uses the ``Ratings`` array, falling back to the top-level ``imdbRating``/``Metascore``
    fields when the array omits them. IMDb rows carry ``imdbVotes``.
    """
    if not data or data.get("Response") != "True":
        return []
    out: dict[str, dict] = {}
    for entry in data.get("Ratings") or []:
        key = _SOURCE_KEYS.get(entry.get("Source", ""))
        score = _parse_score(entry.get("Value", ""))
        if key and score is not None:
            out[key] = {"source": key, "score": score, "raw": entry["Value"].strip()}
    for key, field, scale in (("imdb", "imdbRating", 10), ("metacritic", "Metascore", 100)):
        raw = f"{data.get(field, '')}/{scale}"
        score = _parse_score(raw)
        if key not in out and score is not None:
            out[key] = {"source": key, "score": score, "raw": raw}
    for r in out.values():
        r["votes"] = None
    if "imdb" in out:
        out["imdb"]["votes"] = _parse_votes(data.get("imdbVotes"))
    return [out[k] for k in sorted(out)]


def enrich_item(
    db: Database,
    client: OMDbClient,
    item_id: int,
    imdb_id: str,
    refresh: bool = False,
) -> dict:
    """Fetch OMDb ratings for one item and store them (no commit).

    Raises OMDbQuotaError when OMDb stops answering.
    """
    data = client.get_by_imdb_id(imdb_id, refresh=refresh)
    # raw_cache marks this IMDb id as checked, so later runs skip it (rated or not).
    db.cache_put(PROVIDER, imdb_id, str(client.cache_path(imdb_id)))
    if data.get("Response") != "True":
        db.set_external_ratings(item_id, PROVIDER, [])  # drop scores OMDb no longer has
        return {"status": "not_found", "imdb_id": imdb_id}
    ratings = parse_ratings(data)
    db.set_external_ratings(item_id, PROVIDER, ratings)
    return {"status": "ok", "imdb_id": imdb_id, "ratings": len(ratings)}


def enrich_all(
    db: Database,
    client: OMDbClient,
    item_type: str = "film",
    max_requests: int = DAILY_LIMIT,
    refresh: bool = False,
) -> dict:
    """Store OMDb ratings for all resolved films with an IMDb id.

    IMDb ids already checked (recorded in ``raw_cache``, whether they had scores or not)
    are skipped unless ``refresh``. Cached responses are applied without a request.
    Network calls stop after ``max_requests``, when OMDb reports its daily limit, or after
    ``MAX_CONSECUTIVE_FAILURES`` transport/server errors in a row; re-run later to
    continue. IMDb ids come from the TMDB step (``ingest enrich``, or
    ``ingest backfill-runtime`` for cached TMDB data).
    """
    items = db.execute(
        """SELECT i.id, i.imdb_id FROM items i
           WHERE i.item_type = ? AND i.imdb_id IS NOT NULL
             AND i.match_status IN ('auto', 'manual')
             AND (? OR NOT EXISTS (SELECT 1 FROM raw_cache c
                                   WHERE c.source = ? AND c.external_id = i.imdb_id))
           ORDER BY i.id""",
        (item_type, int(refresh), PROVIDER),
    ).fetchall()
    missing = db.execute(
        """SELECT COUNT(*) AS c FROM items WHERE item_type = ? AND tmdb_id IS NOT NULL
           AND imdb_id IS NULL AND match_status IN ('auto', 'manual')""",
        (item_type,),
    ).fetchone()["c"]

    stats = {
        "total": len(items),
        "no_imdb_id": missing,
        "rated": 0,
        "ratings": 0,
        "not_found": 0,
        "errors": 0,
        "requests": 0,
        "deferred": 0,
        "quota_hit": 0,
        "unavailable": 0,
    }
    start_requests = client.requests_made
    quota_hit = False
    failures_in_row = 0
    logger.info(
        "Fetching OMDb ratings for %d %ss (max %d requests)...", len(items), item_type, max_requests
    )

    for i, row in enumerate(items):
        needs_request = refresh or not client.is_cached(row["imdb_id"])
        if needs_request and (
            quota_hit
            or failures_in_row >= MAX_CONSECUTIVE_FAILURES
            or client.requests_made - start_requests >= max_requests
        ):
            stats["deferred"] += 1
            continue
        try:
            result = enrich_item(db, client, row["id"], row["imdb_id"], refresh=refresh)
        except OMDbQuotaError as e:
            logger.warning("OMDb stopped answering (%s); deferring the rest", e)
            quota_hit = True
            stats["deferred"] += 1
            continue
        except OMDbUnavailableError as e:
            failures_in_row += 1
            stats["errors"] += 1
            logger.error("OMDb error for item %d: %s", row["id"], e)
            if failures_in_row == MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    "OMDb unreachable %d times in a row; deferring the rest", failures_in_row
                )
            continue
        except Exception as e:
            logger.error("OMDb error for item %d: %s", row["id"], e)
            stats["errors"] += 1
            continue
        failures_in_row = 0
        if result["status"] == "ok":
            stats["rated"] += 1
            stats["ratings"] += result["ratings"]
        else:
            stats["not_found"] += 1
        if (i + 1) % 100 == 0:
            db.conn.commit()
            logger.info("OMDb progress: %d/%d", i + 1, len(items))

    db.conn.commit()
    stats["requests"] = client.requests_made - start_requests
    stats["quota_hit"] = int(quota_hit)
    stats["unavailable"] = int(failures_in_row >= MAX_CONSECUTIVE_FAILURES)
    logger.info("OMDb enrichment complete: %s", stats)
    return stats
