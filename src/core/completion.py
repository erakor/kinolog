"""
Director completion tracking and watchlist impact ranking.

Pure feature, completion, and impact calculations, plus database loaders
with TMDB filmography and index-only fallback support.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from src.core.crew import find_people
from src.core.db import Database

RUNTIME_PRESETS: tuple[int, ...] = (90, 105, 120)
MIN_FEATURE_RUNTIME = 40


@dataclass(frozen=True)
class DirectorFilm:
    tmdb_id: int | None
    item_id: int | None  # None if not in the index
    title: str
    year: int | None
    release_date: str | None
    runtime: int | None
    status: str | None
    is_video: bool
    genre_ids: tuple[int, ...]
    seen: bool
    on_watchlist: bool


@dataclass(frozen=True)
class DirectorCompletion:
    person_id: int
    name: str
    seen: int
    total: int
    ratio: float  # 0.0 when total == 0
    coverage: Literal["tmdb", "index_only"]
    films: tuple[DirectorFilm, ...]  # feature films only, sorted by year


@dataclass(frozen=True)
class CompletionDelta:
    person_id: int
    director: str
    film: DirectorFilm
    before_seen: int
    after_seen: int
    total: int
    before_ratio: float
    after_ratio: float
    delta: float  # after_ratio - before_ratio == 1 / total
    completes: bool  # after_seen == total


@dataclass(frozen=True)
class FilmImpact:
    film: DirectorFilm
    deltas: tuple[CompletionDelta, ...]  # one per director (co-directed films)
    impact: float


def format_pct(ratio: float) -> int:
    """Format ratio as rounded percentage (e.g. 5/7 -> 71, 6/7 -> 86)."""
    return int(round(ratio * 100))


def is_feature(
    film: DirectorFilm,
    *,
    today: date,
    min_runtime: int = MIN_FEATURE_RUNTIME,
    include_tv_movies: bool = False,
) -> bool:
    """
    Check if a film is an eligible feature film.

    Rules:
    - Direct-to-video (`is_video: True`) excluded.
    - TV movies (genre 10770) excluded unless `include_tv_movies=True`.
    - Shorts (`runtime < min_runtime`, default 40) excluded, even if seen.
    - Missing runtime (`runtime is None`) is NOT excluded.
    - Status must be 'Released'.
    - Release date must be non-empty and not in the future.
    - Documentaries (genre 99) included.
    """
    if film.is_video:
        return False
    if not include_tv_movies and 10770 in film.genre_ids:
        return False
    if film.runtime is not None and film.runtime < min_runtime:
        return False
    if film.status != "Released":
        return False
    if not film.release_date:
        return False

    try:
        if len(film.release_date) == 4 and film.release_date.isdigit():
            if int(film.release_date) > today.year:
                return False
        else:
            rel_date = date.fromisoformat(film.release_date[:10])
            if rel_date > today:
                return False
    except (ValueError, TypeError):
        return False

    return True


def passes_runtime(
    film: DirectorFilm,
    max_runtime: int | None,
    *,
    include_unknown: bool = False,
) -> bool:
    """Check if film passes candidate runtime filter."""
    if max_runtime is None:
        return True
    if film.runtime is None:
        return include_unknown
    return film.runtime <= max_runtime


def compute_completion(
    person_id: int,
    name: str,
    films: Iterable[DirectorFilm],
    *,
    coverage: Literal["tmdb", "index_only"],
    today: date,
    min_runtime: int = MIN_FEATURE_RUNTIME,
    include_tv_movies: bool = False,
) -> DirectorCompletion:
    """Filter films to features and compute director completion stats."""
    features = [
        f
        for f in films
        if is_feature(
            f,
            today=today,
            min_runtime=min_runtime,
            include_tv_movies=include_tv_movies,
        )
    ]
    # Sorted by year, release_date, title
    features.sort(
        key=lambda f: (f.year if f.year is not None else 9999, f.release_date or "", f.title)
    )

    total = len(features)
    seen = sum(1 for f in features if f.seen)
    ratio = (seen / total) if total > 0 else 0.0

    return DirectorCompletion(
        person_id=person_id,
        name=name,
        seen=seen,
        total=total,
        ratio=ratio,
        coverage=coverage,
        films=tuple(features),
    )


def completion_deltas(
    c: DirectorCompletion,
    *,
    max_runtime: int | None = None,
    include_unknown_runtime: bool = False,
    watchlist_only: bool = False,
) -> list[CompletionDelta]:
    """Compute completion deltas for candidate unseen feature films."""
    deltas: list[CompletionDelta] = []
    if c.total == 0:
        return deltas

    for film in c.films:
        if film.seen:
            continue
        if watchlist_only and not film.on_watchlist:
            continue
        if not passes_runtime(film, max_runtime, include_unknown=include_unknown_runtime):
            continue

        before_seen = c.seen
        after_seen = c.seen + 1
        before_ratio = c.ratio
        after_ratio = after_seen / c.total
        delta = 1.0 / c.total
        completes = after_seen == c.total

        deltas.append(
            CompletionDelta(
                person_id=c.person_id,
                director=c.name,
                film=film,
                before_seen=before_seen,
                after_seen=after_seen,
                total=c.total,
                before_ratio=before_ratio,
                after_ratio=after_ratio,
                delta=delta,
                completes=completes,
            )
        )
    return deltas


def director_impact_key(fi: FilmImpact) -> tuple:
    """Sort key for FilmImpact: (-n_completes, -impact, -max_after_ratio, year or 9999, title)."""
    n_completes = sum(1 for d in fi.deltas if d.completes)
    max_after_ratio = max((d.after_ratio for d in fi.deltas), default=0.0)
    year = fi.film.year if fi.film.year is not None else 9999
    return (-n_completes, -fi.impact, -max_after_ratio, year, fi.film.title)


def aggregate_impact(
    deltas: Iterable[CompletionDelta],
    *,
    min_seen_for_impact: int = 1,
) -> list[FilmImpact]:
    """Aggregate deltas per film and calculate total impact."""
    by_film: dict[DirectorFilm, list[CompletionDelta]] = {}
    for delta in deltas:
        by_film.setdefault(delta.film, []).append(delta)

    results: list[FilmImpact] = []
    for film, film_deltas in by_film.items():
        impact = sum(d.delta for d in film_deltas if d.before_seen >= min_seen_for_impact)
        results.append(
            FilmImpact(
                film=film,
                deltas=tuple(film_deltas),
                impact=impact,
            )
        )

    results.sort(key=director_impact_key)
    return results


def load_director_films(
    db: Database,
    person_id: int,
) -> tuple[list[DirectorFilm], Literal["tmdb", "index_only"]]:
    """
    Load all films for a director.
    Returns (films, coverage) where coverage is 'tmdb' or 'index_only'.
    """
    has_pf = (
        db.execute(
            "SELECT 1 FROM person_filmography WHERE person_id = ? AND job = 'Director' LIMIT 1",
            (person_id,),
        ).fetchone()
        is not None
    )

    if not has_pf:
        # Fallback to indexed credits with role 'Director'
        rows = db.execute(
            """SELECT
                i.id AS item_id,
                i.tmdb_id,
                i.title,
                i.year,
                COALESCE(us.seen, 0) AS seen,
                COALESCE(us.on_watchlist, 0) AS on_watchlist,
                tm.release_date,
                tm.runtime,
                tm.status,
                tm.is_video,
                tm.genre_ids
            FROM credits c
            JOIN items i ON c.item_id = i.id
            LEFT JOIN user_status us ON i.id = us.item_id
            LEFT JOIN tmdb_movies tm ON i.tmdb_id = tm.tmdb_id
            WHERE c.person_id = ? AND c.role = 'Director'
            ORDER BY i.year, i.title""",
            (person_id,),
        ).fetchall()

        films: list[DirectorFilm] = []
        seen_items: set[int] = set()
        for r in rows:
            item_id = r["item_id"]
            if item_id in seen_items:
                continue
            seen_items.add(item_id)

            status = r["status"] or "Released"
            release_date = r["release_date"]
            if not release_date and r["year"]:
                release_date = f"{r['year']:04d}-01-01"

            genre_ids = tuple(json.loads(r["genre_ids"])) if r["genre_ids"] else ()
            is_video = bool(r["is_video"]) if r["is_video"] is not None else False

            films.append(
                DirectorFilm(
                    tmdb_id=r["tmdb_id"],
                    item_id=item_id,
                    title=r["title"],
                    year=r["year"],
                    release_date=release_date,
                    runtime=r["runtime"],
                    status=status,
                    is_video=is_video,
                    genre_ids=genre_ids,
                    seen=bool(r["seen"]),
                    on_watchlist=bool(r["on_watchlist"]),
                )
            )
        return films, "index_only"

    # TMDB filmography coverage: union of person_filmography and indexed credits
    pf_rows = db.execute(
        """SELECT
            pf.tmdb_id,
            tm.title,
            tm.original_title,
            tm.release_date,
            tm.year,
            tm.runtime,
            tm.status,
            tm.is_video,
            tm.genre_ids,
            i.id AS item_id,
            COALESCE(us.seen, 0) AS seen,
            COALESCE(us.on_watchlist, 0) AS on_watchlist
        FROM person_filmography pf
        LEFT JOIN tmdb_movies tm ON pf.tmdb_id = tm.tmdb_id
        LEFT JOIN items i ON pf.tmdb_id = i.tmdb_id
        LEFT JOIN user_status us ON i.id = us.item_id
        WHERE pf.person_id = ? AND pf.job = 'Director'
        ORDER BY tm.year, tm.title""",
        (person_id,),
    ).fetchall()

    films_by_tmdb: dict[int, DirectorFilm] = {}
    films_by_item: dict[int, DirectorFilm] = {}
    films_list: list[DirectorFilm] = []

    for r in pf_rows:
        tmdb_id = r["tmdb_id"]
        title = r["title"] or f"TMDB {tmdb_id}"
        genre_ids = tuple(json.loads(r["genre_ids"])) if r["genre_ids"] else ()
        is_video = bool(r["is_video"]) if r["is_video"] is not None else False
        item_id = r["item_id"]
        seen = bool(r["seen"]) if item_id is not None else False
        on_watchlist = bool(r["on_watchlist"]) if item_id is not None else False

        film = DirectorFilm(
            tmdb_id=tmdb_id,
            item_id=item_id,
            title=title,
            year=r["year"],
            release_date=r["release_date"],
            runtime=r["runtime"],
            status=r["status"],
            is_video=is_video,
            genre_ids=genre_ids,
            seen=seen,
            on_watchlist=on_watchlist,
        )
        films_by_tmdb[tmdb_id] = film
        if item_id is not None:
            films_by_item[item_id] = film
        films_list.append(film)

    # Union with indexed credits: seen films or indexed films dropped by TMDB
    cr_rows = db.execute(
        """SELECT
            i.id AS item_id,
            i.tmdb_id,
            i.title,
            i.year,
            COALESCE(us.seen, 0) AS seen,
            COALESCE(us.on_watchlist, 0) AS on_watchlist,
            tm.release_date,
            tm.runtime,
            tm.status,
            tm.is_video,
            tm.genre_ids
        FROM credits c
        JOIN items i ON c.item_id = i.id
        LEFT JOIN user_status us ON i.id = us.item_id
        LEFT JOIN tmdb_movies tm ON i.tmdb_id = tm.tmdb_id
        WHERE c.person_id = ? AND c.role = 'Director'""",
        (person_id,),
    ).fetchall()

    for r in cr_rows:
        tmdb_id = r["tmdb_id"]
        item_id = r["item_id"]
        if tmdb_id is not None and tmdb_id in films_by_tmdb:
            continue
        if item_id is not None and item_id in films_by_item:
            continue

        status = r["status"] or "Released"
        release_date = r["release_date"]
        if not release_date and r["year"]:
            release_date = f"{r['year']:04d}-01-01"

        genre_ids = tuple(json.loads(r["genre_ids"])) if r["genre_ids"] else ()
        is_video = bool(r["is_video"]) if r["is_video"] is not None else False

        film = DirectorFilm(
            tmdb_id=tmdb_id,
            item_id=item_id,
            title=r["title"],
            year=r["year"],
            release_date=release_date,
            runtime=r["runtime"],
            status=status,
            is_video=is_video,
            genre_ids=genre_ids,
            seen=bool(r["seen"]),
            on_watchlist=bool(r["on_watchlist"]),
        )
        if tmdb_id is not None:
            films_by_tmdb[tmdb_id] = film
        if item_id is not None:
            films_by_item[item_id] = film
        films_list.append(film)

    return films_list, "tmdb"


def director_completions(
    db: Database,
    *,
    name: str | None = None,
    person_id: int | None = None,
    min_seen: int = 0,
    min_total: int = 1,
    today: date | None = None,
    **feature_kw,
) -> list[DirectorCompletion]:
    """Load director completions matching criteria, sorted by ratio and seen count."""
    if today is None:
        today = date.today()

    if person_id is not None:
        people = find_people(db, person_id=person_id)
    elif name is not None:
        people = find_people(db, name=name)
    else:
        people = db.execute(
            """SELECT DISTINCT p.id, p.name FROM people p
               WHERE p.id IN (SELECT person_id FROM credits WHERE role = 'Director')
                  OR p.id IN (SELECT person_id FROM person_filmography WHERE job = 'Director')
               ORDER BY p.name"""
        ).fetchall()

    results: list[DirectorCompletion] = []
    for p in people:
        films, coverage = load_director_films(db, p["id"])
        comp = compute_completion(
            p["id"],
            p["name"],
            films,
            coverage=coverage,
            today=today,
            **feature_kw,
        )
        if comp.seen >= min_seen and comp.total >= min_total:
            results.append(comp)

    results.sort(key=lambda c: (-c.ratio, -c.seen, -c.total, c.name))
    return results


def watchlist_by_director_impact(
    db: Database,
    *,
    max_runtime: int | None = None,
    include_unknown_runtime: bool = False,
    include_unseen: bool = False,
    limit: int | None = None,
    today: date | None = None,
) -> list[FilmImpact]:
    """Rank watchlist (or unseen) films by sum of director completion deltas."""
    if today is None:
        today = date.today()

    completions = director_completions(db, min_seen=0, min_total=1, today=today)
    all_deltas: list[CompletionDelta] = []
    for c in completions:
        deltas = completion_deltas(
            c,
            max_runtime=max_runtime,
            include_unknown_runtime=include_unknown_runtime,
            watchlist_only=not include_unseen,
        )
        all_deltas.extend(deltas)

    impacts = aggregate_impact(all_deltas, min_seen_for_impact=1)
    if limit is not None:
        impacts = impacts[:limit]
    return impacts
