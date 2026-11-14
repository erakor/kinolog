"""
Filmography enricher: fetch TMDB filmographies for directors.

Fetches /person/{id}/movie_credits for directors and details for each film,
storing metadata in tmdb_movies and person_filmography tables.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from src.core.crew import find_people
from src.core.db import Database
from src.ingest.resolvers.tmdb import CACHE_DIR, TMDBResolver

logger = logging.getLogger(__name__)


def enrich_director_filmography(
    db: Database,
    resolver: TMDBResolver,
    person_id: int,
    *,
    fetch_details: bool = True,
    refresh: bool = False,
) -> dict:
    """
    Enrich a single director's filmography from TMDB.

    Fetches person movie credits and caches details for each director credit.
    """
    person = db.execute(
        "SELECT id, name, tmdb_person_id FROM people WHERE id = ?",
        (person_id,),
    ).fetchone()

    if not person:
        return {"status": "error", "reason": "person_not_found"}

    tmdb_person_id = person["tmdb_person_id"]
    if not tmdb_person_id:
        return {"status": "skipped", "reason": "no_tmdb_person_id"}

    # Fetch person movie credits
    credits_data = resolver.get_person_movie_credits(tmdb_person_id, refresh=refresh)

    # Record in raw_cache
    person_cache_path = str(CACHE_DIR / f"person_{tmdb_person_id}_movie_credits.json")
    db.cache_put("tmdb_person_movie_credits", str(tmdb_person_id), person_cache_path)

    director_count = 0
    now_iso = datetime.now(UTC).isoformat()

    # Filter to job == "Director" only (exclude Co-Director, Assistant Director, etc.)
    for credit in credits_data.get("crew", []):
        if credit.get("job") != "Director":
            continue

        tmdb_id = credit["id"]
        director_count += 1

        if fetch_details:
            details = resolver.get_details(tmdb_id)
            movie_cache_path = str(CACHE_DIR / f"movie_{tmdb_id}.json")
            db.cache_put("tmdb", str(tmdb_id), movie_cache_path)

            title = details.get("title") or credit.get("title") or ""
            orig_title = details.get("original_title") or credit.get("original_title")
            rel_date = details.get("release_date") or credit.get("release_date")
            runtime = details.get("runtime")
            if runtime == 0:
                runtime = None
            status = details.get("status") or "Released"
            is_video = 1 if (details.get("video") or credit.get("video")) else 0

            genres = details.get("genres")
            if genres is not None:
                genre_ids = [g["id"] for g in genres if isinstance(g, dict) and "id" in g]
            else:
                genre_ids = credit.get("genre_ids", [])
        else:
            title = credit.get("title") or ""
            orig_title = credit.get("original_title")
            rel_date = credit.get("release_date")
            runtime = None
            status = None
            is_video = 1 if credit.get("video") else 0
            genre_ids = credit.get("genre_ids", [])

        year = None
        if rel_date and len(rel_date) >= 4 and rel_date[:4].isdigit():
            year = int(rel_date[:4])

        genre_ids_json = json.dumps(genre_ids)

        db.execute(
            """INSERT OR REPLACE INTO tmdb_movies (
                tmdb_id, title, original_title, release_date, year,
                runtime, status, is_video, genre_ids, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tmdb_id,
                title,
                orig_title,
                rel_date,
                year,
                runtime,
                status,
                is_video,
                genre_ids_json,
                now_iso,
            ),
        )

        db.execute(
            """INSERT OR REPLACE INTO person_filmography (person_id, tmdb_id, job)
               VALUES (?, ?, 'Director')""",
            (person_id, tmdb_id),
        )

    db.conn.commit()
    return {
        "status": "success",
        "person_id": person_id,
        "name": person["name"],
        "tmdb_person_id": tmdb_person_id,
        "director_films": director_count,
    }


def enrich_all_filmographies(
    db: Database,
    resolver: TMDBResolver,
    *,
    min_seen: int = 2,
    person_name: str | None = None,
    limit: int | None = None,
    fetch_details: bool = True,
    refresh: bool = False,
) -> dict:
    """
    Enrich filmographies for all directors with at least min_seen films (or matching name).
    """
    if person_name is not None:
        raw_people = find_people(db, name=person_name)
        # Fetch full person rows with tmdb_person_id
        people = []
        for p in raw_people:
            full = db.execute(
                "SELECT id, name, tmdb_person_id FROM people WHERE id = ?",
                (p["id"],),
            ).fetchone()
            if full:
                people.append(full)
    else:
        people = db.execute(
            """SELECT p.id, p.name, p.tmdb_person_id,
                      COUNT(DISTINCT cr.item_id) as seen_count
               FROM people p
               JOIN credits cr ON p.id = cr.person_id
               JOIN user_status us ON cr.item_id = us.item_id
               WHERE cr.role = 'Director' AND us.seen = 1
               GROUP BY p.id
               HAVING seen_count >= ?
               ORDER BY seen_count DESC, p.name""",
            (min_seen,),
        ).fetchall()

    if limit is not None:
        people = people[:limit]

    stats = {
        "total_directors": len(people),
        "enriched": 0,
        "skipped_no_tmdb": 0,
        "director_credits": 0,
    }

    for p in people:
        if not p["tmdb_person_id"]:
            stats["skipped_no_tmdb"] += 1
            continue

        res = enrich_director_filmography(
            db,
            resolver,
            p["id"],
            fetch_details=fetch_details,
            refresh=refresh,
        )
        stats["enriched"] += 1
        stats["director_credits"] += res.get("director_films", 0)

    return stats
