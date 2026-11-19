"""Director collections: how close you are to completing each filmography.

Definitions (see docs/web-ui-plan.md):
- ``total`` counts the director's films *in the index* (no TMDB filmography fetch).
- Shorts (runtime_min <= 40) and TV movies (is_tv = 1) are excluded from ``seen`` and ``total``.
- Films with unknown runtime are counted (they cannot be classified); detail rows flag them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kinolog.domain import SHORT_MAX_MIN
from kinolog.store import Database, InvalidInputError, chunked

SORTS = ("pct", "hearted", "name", "remaining")
STATUSES = ("all", "in_progress", "completed")

# SQL fragment (alias i) selecting the films that count toward a collection.
COUNTED = (
    "i.item_type = 'film' AND COALESCE(i.is_tv, 0) = 0 "
    f"AND (i.runtime_min IS NULL OR i.runtime_min > {SHORT_MAX_MIN})"
)


@dataclass
class DirectorFilm:
    item_id: int
    title: str
    year: int | None
    runtime_min: int | None
    seen: bool
    liked: bool
    on_watchlist: bool
    rating: int | None
    runtime_unknown: bool = False


@dataclass
class DirectorCompletion:
    person_id: int
    name: str
    seen: int
    total: int
    pct: float
    hearted: int = 0
    unseen_on_watchlist: int = 0
    films: list[DirectorFilm] | None = None


@dataclass
class CompletionDelta:
    person_id: int
    name: str
    seen: int
    total: int
    before_pct: float
    after_pct: float
    remaining: list[dict] = field(default_factory=list)


_AGG_SQL = f"""
    SELECT p.id AS person_id, p.name,
           COUNT(DISTINCT i.id) AS total,
           COUNT(DISTINCT CASE WHEN us.seen = 1 THEN i.id END) AS seen,
           COUNT(DISTINCT CASE WHEN us.liked = 1 THEN i.id END) AS hearted,
           COUNT(DISTINCT CASE WHEN COALESCE(us.seen, 0) = 0 AND us.on_watchlist = 1
                               THEN i.id END) AS queued
    FROM credits c
    JOIN people p ON p.id = c.person_id
    JOIN items i ON i.id = c.item_id
    LEFT JOIN user_status us ON us.item_id = i.id
    WHERE c.role = ? AND {COUNTED}
"""


def pct(seen: int, total: int) -> float:
    return round(100.0 * seen / total, 1) if total else 0.0


def _films_for(db: Database, person_ids: list[int], role: str) -> dict[int, list[DirectorFilm]]:
    rows = []
    for part in chunked(list(person_ids)):
        ph = ",".join("?" for _ in part)
        rows += db.execute(
            f"""SELECT DISTINCT c.person_id, i.id, i.title, i.year, i.runtime_min,
                       COALESCE(us.seen, 0) AS seen, COALESCE(us.liked, 0) AS liked,
                       COALESCE(us.on_watchlist, 0) AS on_watchlist, us.rating
                FROM credits c JOIN items i ON i.id = c.item_id
                LEFT JOIN user_status us ON us.item_id = i.id
                WHERE c.role = ? AND c.person_id IN ({ph}) AND {COUNTED}
                ORDER BY i.year, i.title""",
            (role, *part),
        ).fetchall()
    rows.sort(key=lambda r: (r["year"] is None, r["year"] or 0, r["title"]))
    out: dict[int, list[DirectorFilm]] = {}
    for r in rows:
        out.setdefault(r["person_id"], []).append(
            DirectorFilm(
                item_id=r["id"],
                title=r["title"],
                year=r["year"],
                runtime_min=r["runtime_min"],
                seen=bool(r["seen"]),
                liked=bool(r["liked"]),
                on_watchlist=bool(r["on_watchlist"]),
                rating=r["rating"],
                runtime_unknown=r["runtime_min"] is None,
            )
        )
    return out


def attach_films(
    db: Database, directors: list[DirectorCompletion], role: str = "Director"
) -> list[DirectorCompletion]:
    """Fill ``films`` for the given directors with one query."""
    films = _films_for(db, [d.person_id for d in directors], role)
    for d in directors:
        d.films = films.get(d.person_id, [])
    return directors


def best_gain(deltas: list[CompletionDelta]) -> float:
    """Largest completion jump (in percentage points) among an item's directors."""
    return max((d.after_pct - d.before_pct for d in deltas), default=0.0)


def _summary_from_row(r: Any) -> DirectorCompletion:
    return DirectorCompletion(
        person_id=r["person_id"],
        name=r["name"],
        seen=r["seen"],
        total=r["total"],
        pct=pct(r["seen"], r["total"]),
        hearted=r["hearted"],
        unseen_on_watchlist=r["queued"],
    )


def director_completion(
    db: Database,
    *,
    role: str = "Director",
    min_films: int = 2,
    sort: str = "pct",
    status: str = "all",
    q: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    with_films: bool = False,
) -> list[DirectorCompletion]:
    """Per-director completion, one query (plus one for films when ``with_films``)."""
    if sort not in SORTS:
        raise InvalidInputError(f"Unknown sort: {sort}")
    if status not in STATUSES:
        raise InvalidInputError(f"Unknown status: {status}")
    rows = db.execute(_AGG_SQL + " GROUP BY p.id HAVING total >= ?", (role, min_films)).fetchall()
    result = [_summary_from_row(r) for r in rows]

    if status == "in_progress":
        result = [d for d in result if 0 < d.seen < d.total]
    elif status == "completed":
        result = [d for d in result if d.seen == d.total]

    if sort == "pct":
        result.sort(key=lambda d: (-d.pct, -d.total, d.name.lower()))
    elif sort == "hearted":
        result.sort(key=lambda d: (-d.hearted, -d.pct, d.name.lower()))
    elif sort == "remaining":
        result.sort(key=lambda d: (d.total == d.seen, d.total - d.seen, d.name.lower()))
    else:
        result.sort(key=lambda d: d.name.lower())

    if q:
        needle = q.strip().lower()
        if needle:
            title_hits = _directors_with_title(db, needle, role)
            result = [d for d in result if needle in d.name.lower() or d.person_id in title_hits]

    result = result[offset:] if limit is None else result[offset : offset + limit]
    if with_films:
        attach_films(db, result, role)
    return result


def _directors_with_title(db: Database, needle: str, role: str) -> set[int]:
    rows = db.execute(
        f"""SELECT DISTINCT c.person_id FROM credits c JOIN items i ON i.id = c.item_id
            WHERE c.role = ? AND {COUNTED} AND lower(i.title) LIKE ?""",
        (role, f"%{needle}%"),
    ).fetchall()
    return {r["person_id"] for r in rows}


def collection_summary(db: Database, *, role: str = "Director", min_films: int = 2) -> dict:
    """Header numbers: tracked directors, above 50%, fully completed."""
    allc = director_completion(db, role=role, min_films=min_films)
    return {
        "tracked": len(allc),
        "above_50": sum(1 for d in allc if d.pct > 50),
        "completed": sum(1 for d in allc if d.total and d.seen == d.total),
    }


def director_detail(
    db: Database, person_id: int, role: str = "Director"
) -> DirectorCompletion | None:
    row = db.execute(_AGG_SQL + " AND p.id = ? GROUP BY p.id", (role, person_id)).fetchone()
    if not row:
        return None
    d = _summary_from_row(row)
    d.films = _films_for(db, [person_id], role).get(person_id, [])
    return d


def completion_deltas(
    db: Database,
    item_ids: list[int],
    *,
    role: str = "Director",
    min_films: int = 2,
    with_remaining: bool = False,
) -> dict[int, list[CompletionDelta]]:
    """What watching each item would do to its directors' completion (batched).

    Every requested id is present in the result. Seen items, shorts, TV and directors below
    ``min_films`` give ``[]``, never a negative delta.
    """
    out: dict[int, list[CompletionDelta]] = {i: [] for i in item_ids}
    if not item_ids:
        return out
    pairs = []
    for part in chunked(list(item_ids)):
        ph = ",".join("?" for _ in part)
        pairs += db.execute(
            f"""SELECT DISTINCT c.item_id, c.person_id FROM credits c
                JOIN items i ON i.id = c.item_id
                LEFT JOIN user_status us ON us.item_id = i.id
                WHERE c.role = ? AND c.item_id IN ({ph}) AND {COUNTED}
                  AND COALESCE(us.seen, 0) = 0""",
            (role, *part),
        ).fetchall()
    if not pairs:
        return out
    person_ids = sorted({r["person_id"] for r in pairs})
    stats = {}
    for part in chunked(person_ids):
        pph = ",".join("?" for _ in part)
        for r in db.execute(
            _AGG_SQL + f" AND p.id IN ({pph}) GROUP BY p.id", (role, *part)
        ).fetchall():
            stats[r["person_id"]] = r
    unseen: dict[int, list[DirectorFilm]] = {}
    if with_remaining:
        unseen = {
            pid: [f for f in films if not f.seen]
            for pid, films in _films_for(db, person_ids, role).items()
        }
    for r in pairs:
        s = stats.get(r["person_id"])
        if not s or s["total"] < min_films:
            continue
        remaining = []
        if with_remaining:
            remaining = [
                {"item_id": f.item_id, "title": f.title, "year": f.year}
                for f in unseen.get(r["person_id"], [])
                if f.item_id != r["item_id"]
            ][:3]
        out[r["item_id"]].append(
            CompletionDelta(
                person_id=r["person_id"],
                name=s["name"],
                seen=s["seen"],
                total=s["total"],
                before_pct=pct(s["seen"], s["total"]),
                after_pct=pct(s["seen"] + 1, s["total"]),
                remaining=remaining,
            )
        )
    for deltas in out.values():
        deltas.sort(key=lambda d: -(d.after_pct - d.before_pct))
    return out
