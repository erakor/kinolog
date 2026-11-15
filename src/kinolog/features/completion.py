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
- Unreleased films (status other than "Released", no release date, or a date after ``today``)
  are excluded. Documentaries are included.
- A missing runtime still counts toward the total; it is excluded from runtime-filtered
  candidate lists unless ``include_unknown_runtime``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from kinolog.domain import SHORT_MAX_MIN

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
    return int(ratio * 100 + 0.5)


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
    n_completes = sum(1 for d in fi.deltas if d.completes)
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
