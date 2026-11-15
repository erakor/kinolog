"""Filmography completion over the full TMDB filmography, and watchlist impact ranking.

``features/collections.py`` is the index-only model that the web UI uses: ``total`` counts the
director's films that are in the index. This module is the opt-in, more accurate one: when a
director's full filmography has been fetched (``ingest filmographies``), ``total`` counts every
feature film they directed, indexed or not. Directors without a fetched filmography fall back to
their indexed credits and are flagged ``coverage="index_only"`` so callers can warn that the
total may be low.

The first half of this file is pure (dataclasses and functions, no database). The loaders at
the bottom read the tables and call the pure functions.

Feature-film rules (same short/TV policy as ``collections.py``):
- Only ``Director`` credits count; direct-to-video and TV movies (``is_tv`` or genre 10770,
  unless ``include_tv_movies``) are excluded.
- Shorts (``runtime <= SHORT_MAX_MIN``) are excluded even when seen.
- Unseen films that are unreleased (status other than "Released", no release date, or a date
  after ``today``) are excluded; a seen film always counts. Documentaries are included.
- A missing runtime still counts toward the total; it is excluded from runtime-filtered
  candidate lists unless ``include_unknown_runtime``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from kinolog.domain import SHORT_MAX_MIN
from kinolog.features.crew import find_people
from kinolog.store import Database

RUNTIME_PRESETS: tuple[int, ...] = (90, 105, 120)
TV_MOVIE_GENRE = 10770

Coverage = Literal["tmdb", "index_only"]


@dataclass(frozen=True)
class FilmographyFilm:
    tmdb_id: int | None
    item_id: int | None  # None if the film is not in the index
    title: str
    year: int | None
    release_date: str | None
    runtime: int | None
    status: str | None
    is_video: bool
    genre_ids: tuple[int, ...]
    seen: bool
    on_watchlist: bool
    is_tv: bool = False


@dataclass(frozen=True)
class FilmographyCompletion:
    person_id: int
    name: str
    seen: int
    total: int
    ratio: float  # 0.0 when total == 0
    coverage: Coverage
    films: tuple[FilmographyFilm, ...]  # feature films only, sorted by year


@dataclass(frozen=True)
class FilmDelta:
    person_id: int
    director: str
    film: FilmographyFilm
    before_seen: int
    after_seen: int
    total: int
    before_ratio: float
    after_ratio: float
    delta: float  # after_ratio - before_ratio == 1 / total
    completes: bool  # after_seen == total


@dataclass(frozen=True)
class FilmImpact:
    film: FilmographyFilm
    deltas: tuple[FilmDelta, ...]  # one per director (co-directed films)
    impact: float


def format_pct(ratio: float) -> int:
    """Whole-number percentage, halves rounded up: 5/7 -> 71, 6/7 -> 86, 1/8 -> 13."""
    return int(ratio * 100 + 0.5 + 1e-9)  # epsilon: 0.145 * 100 is 14.499999999999998


def _released_by(release_date: str, today: date) -> bool:
    try:
        if len(release_date) == 4 and release_date.isdigit():
            return int(release_date) <= today.year
        return date.fromisoformat(release_date[:10]) <= today
    except ValueError:
        return False


def is_feature(
    film: FilmographyFilm,
    *,
    today: date,
    max_short_runtime: int = SHORT_MAX_MIN,
    include_tv_movies: bool = False,
) -> bool:
    """Whether the film counts toward a director's completion (see the module docstring)."""
    if film.is_video:
        return False
    if not include_tv_movies and (film.is_tv or TV_MOVIE_GENRE in film.genre_ids):
        return False
    if film.runtime is not None and film.runtime <= max_short_runtime:
        return False
    if film.seen:
        return True  # watched, so it was released whatever TMDB's status says
    if film.status != "Released" or not film.release_date:
        return False
    return _released_by(film.release_date, today)


def passes_runtime(
    film: FilmographyFilm, max_runtime: int | None, *, include_unknown: bool = False
) -> bool:
    """Candidate runtime filter. It narrows candidates only, never a director's total."""
    if max_runtime is None:
        return True
    if film.runtime is None:
        return include_unknown
    return film.runtime <= max_runtime


def compute_completion(
    person_id: int,
    name: str,
    films: Iterable[FilmographyFilm],
    *,
    coverage: Coverage,
    today: date,
    max_short_runtime: int = SHORT_MAX_MIN,
    include_tv_movies: bool = False,
) -> FilmographyCompletion:
    """Keep the feature films and count how many the user has seen."""
    features = [
        f
        for f in films
        if is_feature(
            f, today=today, max_short_runtime=max_short_runtime, include_tv_movies=include_tv_movies
        )
    ]
    features.sort(
        key=lambda f: (f.year if f.year is not None else 9999, f.release_date or "", f.title)
    )
    total = len(features)
    seen = sum(1 for f in features if f.seen)
    return FilmographyCompletion(
        person_id=person_id,
        name=name,
        seen=seen,
        total=total,
        ratio=seen / total if total else 0.0,
        coverage=coverage,
        films=tuple(features),
    )


def completion_deltas(
    c: FilmographyCompletion,
    *,
    max_runtime: int | None = None,
    include_unknown_runtime: bool = False,
    watchlist_only: bool = False,
) -> list[FilmDelta]:
    """What watching each candidate (an unseen feature film) would do to this director."""
    if c.total == 0:
        return []
    out = []
    for film in c.films:
        if film.seen or (watchlist_only and not film.on_watchlist):
            continue
        if not passes_runtime(film, max_runtime, include_unknown=include_unknown_runtime):
            continue
        after_seen = c.seen + 1
        out.append(
            FilmDelta(
                person_id=c.person_id,
                director=c.name,
                film=film,
                before_seen=c.seen,
                after_seen=after_seen,
                total=c.total,
                before_ratio=c.ratio,
                after_ratio=after_seen / c.total,
                delta=1.0 / c.total,
                completes=after_seen == c.total,
            )
        )
    return out


def _film_key(film: FilmographyFilm) -> tuple:
    """Identity of a film across directors (a co-directed film appears once per director)."""
    if film.tmdb_id is not None or film.item_id is not None:
        return ("id", film.tmdb_id, film.item_id)
    return ("title", film.title, film.year)


def director_impact_key(fi: FilmImpact) -> tuple:
    """Sort key: completions first, then impact, then the highest reached ratio, then year/title."""
    # A debut by an unseen director (0/1 -> 1/1) is not a completion worth promoting.
    n_completes = sum(1 for d in fi.deltas if d.completes and d.before_seen >= 1)
    max_after = max((d.after_ratio for d in fi.deltas), default=0.0)
    year = fi.film.year if fi.film.year is not None else 9999
    return (-n_completes, -fi.impact, -max_after, year, fi.film.title)


def aggregate_impact(
    deltas: Iterable[FilmDelta], *, min_seen_for_impact: int = 1
) -> list[FilmImpact]:
    """Group deltas by film. Impact sums the deltas of directors with enough films seen.

    ``min_seen_for_impact=1`` keeps a debut by an unseen director (0/1 -> 1/1) from flooding the
    list; such a delta stays on the film but adds nothing to its impact.
    """
    by_film: dict[tuple, list[FilmDelta]] = {}
    for d in deltas:
        by_film.setdefault(_film_key(d.film), []).append(d)
    results = [
        FilmImpact(
            film=ds[0].film,
            deltas=tuple(ds),
            impact=sum(d.delta for d in ds if d.before_seen >= min_seen_for_impact),
        )
        for ds in by_film.values()
    ]
    results.sort(key=director_impact_key)
    return results


# --- Loaders ---

_FILM_COLUMNS = """
    i.id AS item_id, COALESCE(i.tmdb_id, tm.tmdb_id) AS tmdb_id,
    i.title AS item_title, i.year AS item_year, i.runtime_min, COALESCE(i.is_tv, 0) AS is_tv,
    COALESCE(us.seen, 0) AS seen, COALESCE(us.on_watchlist, 0) AS on_watchlist,
    tm.title AS tm_title, tm.year AS tm_year, tm.release_date, tm.runtime, tm.status,
    tm.is_video, tm.genre_ids
"""


def _film_from_row(r: Any) -> FilmographyFilm:
    """Merge an item row and/or a ``tmdb_movies`` row. TMDB facts win; the index fills gaps."""
    indexed = r["item_id"] is not None
    year = r["tm_year"] or r["item_year"]
    release_date = r["release_date"] or (f"{year:04d}-01-01" if indexed and year else None)
    return FilmographyFilm(
        tmdb_id=r["tmdb_id"],
        item_id=r["item_id"],
        title=r["tm_title"] or r["item_title"] or f"TMDB {r['tmdb_id']}",
        year=year,
        release_date=release_date,
        runtime=r["runtime"] or r["runtime_min"] or None,
        # A film in the index that TMDB never described is assumed released.
        status=r["status"] or ("Released" if indexed else None),
        is_video=bool(r["is_video"]),
        genre_ids=tuple(json.loads(r["genre_ids"])) if r["genre_ids"] else (),
        seen=bool(r["seen"]),
        on_watchlist=bool(r["on_watchlist"]),
        is_tv=bool(r["is_tv"]),
    )


def _indexed_director_films(db: Database, person_id: int) -> list[FilmographyFilm]:
    rows = db.execute(
        f"""SELECT DISTINCT {_FILM_COLUMNS}
            FROM credits c
            JOIN items i ON i.id = c.item_id
            LEFT JOIN user_status us ON us.item_id = i.id
            LEFT JOIN tmdb_movies tm ON tm.tmdb_id = i.tmdb_id
            WHERE c.person_id = ? AND c.role = 'Director' AND i.item_type = 'film'""",
        (person_id,),
    ).fetchall()
    return [_film_from_row(r) for r in rows]


def _tmdb_director_films(db: Database, person_id: int) -> list[FilmographyFilm]:
    rows = db.execute(
        f"""SELECT DISTINCT {_FILM_COLUMNS}
            FROM person_filmography pf
            LEFT JOIN tmdb_movies tm ON tm.tmdb_id = pf.tmdb_id
            LEFT JOIN items i ON i.tmdb_id = pf.tmdb_id AND i.item_type = 'film'
            LEFT JOIN user_status us ON us.item_id = i.id
            WHERE pf.person_id = ? AND pf.job = 'Director'""",
        (person_id,),
    ).fetchall()
    return [_film_from_row(r) for r in rows]


def load_director_films(db: Database, person_id: int) -> tuple[list[FilmographyFilm], Coverage]:
    """All of a director's films plus the coverage of the data behind them.

    With a fetched filmography the result is its union with the indexed Director credits, so a
    seen film TMDB dropped from the person's credits still counts. Without one it is the indexed
    credits alone, and coverage is ``"index_only"``.
    """
    indexed = _indexed_director_films(db, person_id)
    tmdb = _tmdb_director_films(db, person_id)
    if not tmdb:
        return indexed, "index_only"
    # Unindexed films without a status (details never fetched) are not counted, so the total
    # may be low: say so rather than claim full coverage.
    undescribed = any(f.status is None and f.item_id is None for f in tmdb)
    known_tmdb = {f.tmdb_id for f in tmdb if f.tmdb_id is not None}
    known_items = {f.item_id for f in tmdb if f.item_id is not None}
    extra = [
        f
        for f in indexed
        if f.item_id not in known_items and (f.tmdb_id is None or f.tmdb_id not in known_tmdb)
    ]
    return [*tmdb, *extra], "index_only" if undescribed else "tmdb"


def _all_directors(db: Database) -> list:
    return db.execute(
        """SELECT p.id, p.name FROM people p
           WHERE p.id IN (SELECT person_id FROM credits WHERE role = 'Director')
              OR p.id IN (SELECT person_id FROM person_filmography WHERE job = 'Director')
           ORDER BY p.name"""
    ).fetchall()


def _people_by_ids(db: Database, person_ids: Iterable[int]) -> list:
    return db.execute(
        "SELECT id, name FROM people WHERE id IN (SELECT value FROM json_each(?)) ORDER BY name",
        (json.dumps(list(person_ids)),),
    ).fetchall()


def director_completions(
    db: Database,
    *,
    name: str | None = None,
    person_id: int | None = None,
    min_seen: int = 0,
    min_total: int = 1,
    person_ids: Iterable[int] | None = None,
    today: date | None = None,
    **feature_kw: Any,
) -> list[FilmographyCompletion]:
    """Completion for the directors matching ``name``/``person_id`` (default: every director).

    Sorted by ratio, then seen, then total, then name. ``feature_kw`` is passed to
    ``compute_completion`` (``max_short_runtime``, ``include_tv_movies``).
    """
    today = today or date.today()
    if not name and person_id is None:
        people = _all_directors(db) if person_ids is None else _people_by_ids(db, person_ids)
    else:
        people = find_people(db, name=name, person_id=person_id)
        if person_ids is not None:
            wanted = set(person_ids)
            people = [p for p in people if p["id"] in wanted]
    results = []
    for p in people:
        films, coverage = load_director_films(db, p["id"])
        c = compute_completion(
            p["id"], p["name"], films, coverage=coverage, today=today, **feature_kw
        )
        if c.seen >= min_seen and c.total >= min_total:
            results.append(c)
    results.sort(key=lambda c: (-c.ratio, -c.seen, -c.total, c.name))
    return results


def _watchlist_director_ids(db: Database) -> list[int]:
    """Directors with at least one unseen watchlist film (the only candidates without
    ``include_unseen``)."""
    rows = db.execute(
        """SELECT person_id FROM credits c
           JOIN user_status us ON us.item_id = c.item_id
           WHERE c.role = 'Director' AND us.on_watchlist = 1 AND COALESCE(us.seen, 0) = 0
           UNION
           SELECT pf.person_id FROM person_filmography pf
           JOIN items i ON i.tmdb_id = pf.tmdb_id AND i.item_type = 'film'
           JOIN user_status us ON us.item_id = i.id
           WHERE pf.job = 'Director' AND us.on_watchlist = 1 AND COALESCE(us.seen, 0) = 0"""
    ).fetchall()
    return [r["person_id"] for r in rows]


def watchlist_by_director_impact(
    db: Database,
    *,
    max_runtime: int | None = None,
    include_unknown_runtime: bool = False,
    include_unseen: bool = False,
    limit: int | None = None,
    today: date | None = None,
) -> list[FilmImpact]:
    """Films ranked by how much watching them would advance their directors' completion.

    Candidates are unseen feature films on the watchlist; ``include_unseen`` adds the director's
    other unseen films, including ones that are not in the index.
    """
    today = today or date.today()
    deltas: list[FilmDelta] = []
    person_ids = None if include_unseen else _watchlist_director_ids(db)
    for c in director_completions(db, person_ids=person_ids, today=today):
        deltas += completion_deltas(
            c,
            max_runtime=max_runtime,
            include_unknown_runtime=include_unknown_runtime,
            watchlist_only=not include_unseen,
        )
    ranked = aggregate_impact(deltas)
    return ranked if limit is None else ranked[:limit]
