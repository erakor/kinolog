"""OMDb enricher: critic and audience scores keyed by the IMDb id TMDB gives us.

TMDB stays the metadata master (titles, credits, overviews, ids). OMDb is only asked for
ratings: one request per film returns IMDb, Rotten Tomatoes and Metacritic scores, which are
normalized to 0..100 and stored in ``external_ratings``. Nothing here is written to
``documents``, so ratings never leak into chunk text or retrieval.

The free tier allows 1,000 requests/day. Responses are disk-cached under ``data/cache/omdb/``
(only definitive answers: a hit or "not found"), so re-runs cost nothing, ``max_requests``
caps network calls per run, and a "Request limit reached" answer stops the batch cleanly.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import httpx

from src.core.db import Database
from src.ingest.resolvers.tmdb import get_api_key

logger = logging.getLogger(__name__)

OMDB_BASE = "https://www.omdbapi.com/"
CACHE_DIR = Path("data/cache/omdb")
PROVIDER = "omdb"
DAILY_LIMIT = 1000

# OMDb "Ratings" array source names -> our source keys
_SOURCE_KEYS = {
    "Internet Movie Database": "imdb",
    "Rotten Tomatoes": "rotten_tomatoes",
    "Metacritic": "metacritic",
}


class OMDbQuotaError(RuntimeError):
    """Daily request limit reached, or the key is invalid/inactive: stop the batch."""


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


class OMDbClient:
    """Minimal OMDb client: lookup by IMDb id, disk-cached, throttled."""

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit: float = 0.1,
        cache_dir: Path = CACHE_DIR,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key or get_api_key("OMDB_API_KEY")
        self.rate_limit = rate_limit
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.requests_made = 0
        self._last_request = 0.0
        self.client = httpx.Client(base_url=OMDB_BASE, timeout=30.0, transport=transport)

    def cache_path(self, imdb_id: str) -> Path:
        return self.cache_dir / f"{imdb_id}.json"

    def is_cached(self, imdb_id: str) -> bool:
        return self.cache_path(imdb_id).exists()

    def _throttle(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def get_by_imdb_id(self, imdb_id: str, refresh: bool = False) -> dict:
        """OMDb title response for an IMDb id (cached unless ``refresh``)."""
        path = self.cache_path(imdb_id)
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))

        self._throttle()
        self.requests_made += 1
        try:
            resp = self.client.get("", params={"i": imdb_id, "apikey": self.api_key})
        except httpx.HTTPError as e:
            # Don't log str(e) for a request error: the URL in it carries the API key.
            raise RuntimeError(f"OMDb request failed for {imdb_id}: {type(e).__name__}") from None
        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError(f"OMDb returned HTTP {resp.status_code} for {imdb_id}") from None

        if data.get("Response") != "True":
            error = str(data.get("Error", ""))
            lowered = error.lower()
            if "limit" in lowered or "api key" in lowered or resp.status_code == 401:
                raise OMDbQuotaError(error or f"HTTP {resp.status_code}")
            if "not found" not in lowered and "incorrect imdb id" not in lowered:
                raise RuntimeError(f"OMDb error for {imdb_id}: {error or resp.status_code}")
            # Definitive "no such title": cache it so it is not re-requested every run.
        elif resp.status_code >= 400:
            raise RuntimeError(f"OMDb returned HTTP {resp.status_code} for {imdb_id}")

        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def close(self):
        self.client.close()


def enrich_item(
    db: Database, client: OMDbClient, item_id: int, imdb_id: str, refresh: bool = False,
) -> dict:
    """Fetch OMDb ratings for one item and store them (no commit).

    Raises OMDbQuotaError when OMDb stops answering.
    """
    data = client.get_by_imdb_id(imdb_id, refresh=refresh)
    db.cache_put(PROVIDER, imdb_id, str(client.cache_path(imdb_id)))
    if data.get("Response") != "True":
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

    Films already rated are skipped unless ``refresh``. Cached responses are applied
    without a request. Network calls stop after ``max_requests`` or when OMDb reports its
    daily limit; re-run tomorrow to continue. IMDb ids come from the TMDB step
    (``ingest enrich``, or ``ingest backfill-runtime`` for cached TMDB data).
    """
    items = db.execute(
        """SELECT i.id, i.imdb_id FROM items i
           WHERE i.item_type = ? AND i.imdb_id IS NOT NULL
             AND i.match_status IN ('auto', 'manual')
             AND (? OR NOT EXISTS (SELECT 1 FROM external_ratings r
                                   WHERE r.item_id = i.id AND r.provider = ?))
           ORDER BY i.id""",
        (item_type, int(refresh), PROVIDER),
    ).fetchall()
    missing = db.execute(
        """SELECT COUNT(*) AS c FROM items WHERE item_type = ? AND tmdb_id IS NOT NULL
           AND imdb_id IS NULL AND match_status IN ('auto', 'manual')""",
        (item_type,),
    ).fetchone()["c"]

    stats = {
        "total": len(items), "no_imdb_id": missing, "rated": 0, "ratings": 0,
        "not_found": 0, "errors": 0, "requests": 0, "deferred": 0, "quota_hit": 0,
    }
    start_requests = client.requests_made
    quota_hit = False
    logger.info("Fetching OMDb ratings for %d %ss (max %d requests)...",
                len(items), item_type, max_requests)

    for i, row in enumerate(items):
        needs_request = refresh or not client.is_cached(row["imdb_id"])
        if needs_request and (
            quota_hit or client.requests_made - start_requests >= max_requests
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
        except Exception as e:
            logger.error("OMDb error for item %d: %s", row["id"], e)
            stats["errors"] += 1
            continue
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
    logger.info("OMDb enrichment complete: %s", stats)
    return stats
