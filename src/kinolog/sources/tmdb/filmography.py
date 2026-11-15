"""Filmography enricher: a director's full TMDB filmography into ``tmdb_movies``.

For each person, ``/person/{id}/movie_credits`` gives their credits; only ``job == "Director"``
is kept (Co-Director, Assistant Director and Second Unit Director are not). Each film's runtime,
status and genres come from the movie details. Those share the ``movie_<id>.json`` disk cache
with ``enrich``, so a film already in the index costs no request and every other film costs one.
TV series are never returned by ``movie_credits``.
"""

from __future__ import annotations

import logging

import httpx

from kinolog.sources.http_cache import read_json
from kinolog.sources.tmdb.client import TMDBClient, person_credits_cache_path, tmdb_cache_path
from kinolog.store import Database

logger = logging.getLogger(__name__)

PERSON_CACHE_SOURCE = "tmdb_person_movie_credits"


def _year(release_date: str | None) -> int | None:
    if release_date and len(release_date) >= 4 and release_date[:4].isdigit():
        return int(release_date[:4])
    return None


def _is_fatal(e: Exception) -> bool:
    """Auth or rate-limit failures hit every request, so they should stop the whole run."""
    return isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403, 429)


def _details_for(client: TMDBClient, tmdb_id: int, fetch: bool) -> dict | None:
    """Movie details: fetched (and cached) when ``fetch``, else only if already on disk."""
    if fetch:
        return client.get_details(tmdb_id)
    path = tmdb_cache_path(tmdb_id)
    return read_json(path) if path.exists() else None


def _movie_facts(credit: dict, details: dict | None) -> dict:
    """Merge a movie_credits row with the (optional) details. Details win."""
    if details is None:
        return {
            "title": credit.get("title") or "",
            "original_title": credit.get("original_title"),
            "release_date": credit.get("release_date"),
            "runtime": None,
            "status": None,  # unknown until details are fetched; not counted as a feature
            "is_video": bool(credit.get("video")),
            "genre_ids": list(credit.get("genre_ids") or []),
        }
    genres = details.get("genres")
    return {
        "title": details.get("title") or credit.get("title") or "",
        "original_title": details.get("original_title") or credit.get("original_title"),
        "release_date": details.get("release_date") or credit.get("release_date"),
        "runtime": details.get("runtime") or None,
        "status": details.get("status"),
        "is_video": bool(details.get("video") or credit.get("video")),
        "genre_ids": (
            [g["id"] for g in genres if isinstance(g, dict) and "id" in g]
            if genres is not None
            else list(credit.get("genre_ids") or [])
        ),
    }


def enrich_director_filmography(
    db: Database,
    client: TMDBClient,
    person_id: int,
    *,
    fetch_details: bool = True,
    refresh: bool = False,
) -> dict:
    """Store one person's Director filmography. Idempotent.

    ``refresh`` re-fetches the person's credits (filmographies grow) but never movie details.
    With ``fetch_details=False`` only details already on disk are used, so films that were never
    described have no status and are not counted until details are fetched.
    """
    person = db.execute(
        "SELECT id, name, tmdb_person_id FROM people WHERE id = ?", (person_id,)
    ).fetchone()
    if not person:
        return {"status": "error", "reason": "person_not_found"}
    tmdb_person_id = person["tmdb_person_id"]
    if not tmdb_person_id:
        return {"status": "skipped", "reason": "no_tmdb_person_id"}

    credits = client.get_person_movie_credits(tmdb_person_id, refresh=refresh)
    person_path = person_credits_cache_path(tmdb_person_id).as_posix()
    db.cache_put(PERSON_CACHE_SOURCE, str(tmdb_person_id), person_path)

    director_ids: list[int] = []
    detail_errors = 0
    for credit in credits.get("crew", []):
        if credit.get("job") != "Director":
            continue
        tmdb_id = credit["id"]
        try:
            details = _details_for(client, tmdb_id, fetch_details)
        except Exception as e:  # one bad film must not abort the director
            if _is_fatal(e):
                raise
            logger.warning("TMDB details failed for %d: %s", tmdb_id, e)
            detail_errors += 1
            details = None
        director_ids.append(tmdb_id)
        if details is None and db.execute(
            "SELECT 1 FROM tmdb_movies WHERE tmdb_id = ?", (tmdb_id,)
        ).fetchone():
            continue  # keep the facts stored earlier rather than replace them with less
        facts = _movie_facts(credit, details)
        db.upsert_tmdb_movie(
            tmdb_id,
            facts["title"],
            original_title=facts["original_title"],
            release_date=facts["release_date"],
            year=_year(facts["release_date"]),
            runtime=facts["runtime"],
            status=facts["status"],
            is_video=facts["is_video"],
            genre_ids=facts["genre_ids"],
            commit=False,
        )

    if "crew" in credits:  # a degraded response without crew must not wipe stored credits
        db.set_person_filmography(person_id, director_ids, "Director", commit=False)
    db.conn.commit()
    return {
        "status": "success",
        "person_id": person_id,
        "name": person["name"],
        "tmdb_person_id": tmdb_person_id,
        "director_films": len(set(director_ids)),
        "detail_errors": detail_errors,
    }


def _target_people(
    db: Database, *, min_seen: int, person_name: str | None, limit: int | None
) -> list:
    if person_name is not None:
        people = db.execute(
            "SELECT id, name, tmdb_person_id FROM people WHERE name LIKE ? ORDER BY name",
            (f"%{person_name}%",),
        ).fetchall()
    else:
        people = db.execute(
            """SELECT p.id, p.name, p.tmdb_person_id, COUNT(DISTINCT cr.item_id) AS seen_count
               FROM people p
               JOIN credits cr ON cr.person_id = p.id
               JOIN user_status us ON us.item_id = cr.item_id
               WHERE cr.role = 'Director' AND us.seen = 1
               GROUP BY p.id
               HAVING seen_count >= ?
               ORDER BY seen_count DESC, p.name""",
            (min_seen,),
        ).fetchall()
    return people if limit is None else people[:limit]


def enrich_all_filmographies(
    db: Database,
    client: TMDBClient,
    *,
    min_seen: int = 2,
    person_name: str | None = None,
    limit: int | None = None,
    fetch_details: bool = True,
    refresh: bool = False,
) -> dict:
    """Enrich every director with at least ``min_seen`` seen films, or those matching a name.

    Directors without a ``tmdb_person_id`` are skipped and counted. A failure for one director is
    counted in ``errors`` and does not stop the run.
    """
    people = _target_people(db, min_seen=min_seen, person_name=person_name, limit=limit)
    stats = {
        "total_directors": len(people),
        "enriched": 0,
        "skipped_no_tmdb": 0,
        "errors": 0,
        "director_credits": 0,
        "detail_errors": 0,
    }
    for p in people:
        if not p["tmdb_person_id"]:
            stats["skipped_no_tmdb"] += 1
            continue
        try:
            res = enrich_director_filmography(
                db, client, p["id"], fetch_details=fetch_details, refresh=refresh
            )
        except Exception as e:
            db.conn.rollback()  # drop this director's half-written rows
            logger.error("Filmography failed for %s: %s", p["name"], e)
            stats["errors"] += 1
            if _is_fatal(e):
                stats["aborted_http_status"] = e.response.status_code
                break
            continue
        stats["enriched"] += 1
        stats["director_credits"] += res["director_films"]
        stats["detail_errors"] += res["detail_errors"]
    return stats
