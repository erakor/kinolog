"""Application services shared by the CLI, the MCP server and the web routes.

Each function takes a ``Database`` (and, where needed, a model provider, a ``taste_fn`` or a
rerank configuration) and returns plain dicts, lists or dataclasses. Services never raise
``HTTPException`` and never take the web lock. Domain errors propagate as ``NotFoundError``,
``InvalidInputError``, ``UnavailableError`` or ``TasteUnavailableError``; each interface maps
them its own way. Cache invalidation after a write stays with the web layer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from typing import Any

from kinolog.config import DEFAULT_RANKER
from kinolog.features import collections as coll
from kinolog.features import completion as fcomp
from kinolog.features.concierge import pick
from kinolog.features.crew import crew_overlap_with_hearts
from kinolog.features.crew import filmography as crew_filmography
from kinolog.features.docfacts import item_facts
from kinolog.retrieval import SearchFilters, search, search_vector
from kinolog.store import Database, InvalidInputError, NotFoundError
from kinolog.taste import RANKERS

ModelProvider = Callable[[], Any]

WATCHLIST_SORTS = ("impact", "added", "runtime", "year", "title", "taste")

DEFAULT_PROMPTS = [
    "I have 90 minutes. Give me a movie.",
    "Help me finish a director I am close to completing",
    "Something tense and sharp under 2 hours",
    "A quiet comfort film from my watch list",
]


class UnavailableError(RuntimeError):
    """A capability the request needs (embedding model, numpy) is not available."""


# --- Search and similarity ---


def search_items(
    db: Database,
    query: str,
    *,
    get_model: ModelProvider | None = None,
    mode: str = "rrf",
    limit: int = 10,
    item_type: str | None = None,
    seen: bool | None = None,
    decade: int | None = None,
) -> list[dict]:
    """Ranked results as plain dicts. Falls back to BM25 when no embedding model is available.

    ``get_model`` is only called for the vector and rrf modes.
    """
    filters = SearchFilters(item_type=item_type, seen=seen, decade=decade)
    model = get_model() if get_model is not None and mode in ("vector", "rrf") else None
    if model is None and mode != "bm25":
        mode = "bm25"
    results = search(db, query, model=model, mode=mode, limit=limit, filters=filters)
    return [
        {
            "title": r.title,
            "year": r.year,
            "score": round(r.score, 4),
            "source": r.source,
            "snippet": r.chunk_text[:200] if r.chunk_text else "",
        }
        for r in results
    ]


def similar_to(
    db: Database,
    title: str,
    *,
    get_model: ModelProvider,
    item_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Items whose embeddings are closest to the first item whose title contains ``title``."""
    item = db.execute("SELECT id FROM items WHERE title LIKE ?", (f"%{title}%",)).fetchone()
    if not item:
        raise NotFoundError(f"Item not found: {title}")

    model = get_model()
    if model is None:
        raise UnavailableError("Embedding model not available")

    vec_table = f"vec_{model.name}"
    row = db.execute(
        f"""SELECT v.embedding FROM {vec_table} v
            JOIN chunks c ON v.chunk_id = c.id
            WHERE c.item_id = ? LIMIT 1""",
        (item["id"],),
    ).fetchone()
    if not row:
        raise NotFoundError(f"No embedding found for: {title}")

    try:
        import numpy as np

        query_embedding = np.frombuffer(row["embedding"], dtype=np.float32)
    except ImportError as e:
        raise UnavailableError("numpy is required for vector operations") from e

    filters = SearchFilters(item_type=item_type)
    results = search_vector(db, query_embedding, model.name, limit=limit + 1, filters=filters)
    # Exclude the query item itself
    return [
        {"title": r.title, "year": r.year, "score": round(r.score, 4)}
        for r in results
        if r.item_id != item["id"]
    ][:limit]


# --- Taste and crew ---


def rank_watchlist(db: Database, ranker: str = DEFAULT_RANKER, limit: int = 20) -> list[dict]:
    """Watchlist items ranked by similarity to hearted films."""
    rank_fn = RANKERS.get(ranker)
    if not rank_fn:
        raise InvalidInputError(f"Unknown ranker: {ranker}")

    candidate_ids = db.get_watchlist_ids()
    heart_ids = db.get_heart_ids()
    scores = rank_fn(db, candidate_ids, heart_ids)

    results = []
    for s in scores[:limit]:
        item = db.get_item(s.item_id)
        if item:
            results.append({
                "title": item["title"],
                "year": item["year"],
                "score": round(s.score, 4),
                "method": s.method,
            })
    return results


def filmography(db: Database, name: str, role: str | None = None) -> list[dict]:
    entries = crew_filmography(db, person_name=name, role=role)
    return [
        {
            "person": entry.person_name,
            "role": entry.role,
            "seen": entry.total_seen,
            "total": entry.total_in_db,
            "films": [
                {"title": f["title"], "year": f.get("year"), "seen": bool(f["seen"])}
                for f in entry.films
            ],
        }
        for entry in entries
    ]


def crew_overlap(db: Database, role: str = "Director", min_overlap: int = 2) -> list[dict]:
    results = crew_overlap_with_hearts(db, role=role, min_overlap=min_overlap)
    return [
        {
            "person": r.person_name,
            "role": r.role,
            "heart_count": r.overlap_count,
            "seen_count": r.total_seen,
            "films": [f["title"] for f in r.films],
        }
        for r in results
    ]


def _pct(ratio: float) -> int:
    return fcomp.format_pct(ratio)


def _positive(name: str, value: int | None, minimum: int = 1) -> None:
    if value is not None and value < minimum:
        raise InvalidInputError(f"{name} must be at least {minimum}")


def filmography_completion(
    db: Database,
    *,
    name: str | None = None,
    min_seen: int | None = None,
    min_total: int | None = None,
    limit: int | None = 25,
    today: date | None = None,
) -> list[dict]:
    """Director completion against the full TMDB filmography, where it has been fetched.

    Directors without a fetched filmography use their indexed credits and report
    ``coverage="index_only"`` (the total may be low; run ``ingest filmographies``). With a
    ``name`` the result carries each director's feature films with an ``if_watched`` preview for
    the unseen ones, and the default thresholds drop to 0 seen / 1 film.
    """
    min_seen = (0 if name else 1) if min_seen is None else min_seen
    min_total = (1 if name else 2) if min_total is None else min_total
    _positive("min_seen", min_seen, 0)
    _positive("min_total", min_total)
    _positive("limit", limit)
    found = fcomp.director_completions(
        db, name=name, min_seen=min_seen, min_total=min_total, today=today
    )
    if limit is not None:
        found = found[:limit]
    out = []
    for c in found:
        row: dict[str, Any] = {
            "person_id": c.person_id,
            "person": c.name,
            "seen": c.seen,
            "total": c.total,
            "percent": _pct(c.ratio),
            "coverage": c.coverage,
        }
        if name:
            preview = {d.film: d for d in fcomp.completion_deltas(c)}
            row["films"] = [_completion_film(f, preview.get(f)) for f in c.films]
        out.append(row)
    return out


def _completion_film(f: fcomp.FilmographyFilm, d: fcomp.FilmDelta | None) -> dict:
    return {
        "title": f.title,
        "year": f.year,
        "runtime": f.runtime,
        "seen": f.seen,
        "on_watchlist": f.on_watchlist,
        "in_index": f.item_id is not None,
        "if_watched": None if d is None else {
            "before": f"{d.before_seen}/{d.total}",
            "after": f"{d.after_seen}/{d.total}",
            "before_pct": _pct(d.before_ratio),
            "after_pct": _pct(d.after_ratio),
            "completes": d.completes,
        },
    }


def watchlist_director_impact(
    db: Database,
    *,
    max_runtime: int | None = None,
    include_unseen: bool = False,
    include_unknown_runtime: bool = False,
    limit: int | None = 20,
    today: date | None = None,
) -> list[dict]:
    """Watchlist films ranked by how much they would advance their directors' completion.

    ``include_unseen`` also considers unseen films that are not on the watchlist (including ones
    outside the index). ``max_runtime`` narrows candidates only, never a director's total.
    """
    _positive("max_runtime", max_runtime)
    _positive("limit", limit)
    ranked = fcomp.watchlist_by_director_impact(
        db, max_runtime=max_runtime, include_unseen=include_unseen,
        include_unknown_runtime=include_unknown_runtime, limit=limit, today=today,
    )
    return [
        {
            "title": fi.film.title,
            "year": fi.film.year,
            "runtime": fi.film.runtime,
            "on_watchlist": fi.film.on_watchlist,
            "in_index": fi.film.item_id is not None,
            "impact": round(fi.impact, 4),
            "directors": [
                {
                    "person": d.director,
                    "before": f"{d.before_seen}/{d.total}",
                    "after": f"{d.after_seen}/{d.total}",
                    "before_pct": _pct(d.before_ratio),
                    "after_pct": _pct(d.after_ratio),
                    "completes": d.completes,
                }
                for d in fi.deltas
            ],
        }
        for fi in ranked
    ]


def stats(db: Database) -> dict:
    s = db.stats()
    queue = db.get_review_queue()
    matched = db.execute("SELECT COUNT(*) as c FROM items WHERE tmdb_id IS NOT NULL").fetchone()
    s["review_queue"] = len(queue)
    s["items_matched"] = matched["c"]
    return s


# --- Items and the watch log ---


def require_card(db: Database, item_id: int) -> dict:
    """The item's UI card; raises NotFoundError if there is no such item."""
    card = db.get_item_card(item_id)
    if card is None:
        raise NotFoundError(f"No such item: {item_id}")
    return card


def item_detail(db: Database, item_id: int) -> dict:
    return {**require_card(db, item_id), "sources": db.get_item_sources(item_id)}


def rate_item(db: Database, item_id: int, rating: int | None) -> dict:
    require_card(db, item_id)
    db.set_rating(item_id, rating)
    return db.get_item_card(item_id)


def like_item(db: Database, item_id: int, liked: bool | None) -> dict:
    require_card(db, item_id)
    db.set_liked(item_id, liked)
    return db.get_item_card(item_id)


def create_log_entry(
    db: Database,
    item_id: int,
    watched_on: str,
    *,
    rating: int | None = None,
    liked: bool | None = None,
    rewatch: bool = False,
) -> dict:
    """Log a viewing; a logged film is no longer queued."""
    card = require_card(db, item_id)
    entry_id = db.log_watch(item_id, watched_on, rating=rating, liked=liked, rewatch=rewatch)
    if card["status"]["on_watchlist"]:
        db.set_watchlist(item_id, False)
    return db.get_watch_entry_view(entry_id)


# --- Watchlist ---


def add_to_watchlist(db: Database, item_id: int) -> dict:
    require_card(db, item_id)
    db.set_watchlist(item_id, True)
    return db.get_item_card(item_id)


def remove_from_watchlist(db: Database, item_id: int) -> dict:
    require_card(db, item_id)
    db.set_watchlist(item_id, False)
    return db.get_item_card(item_id)


def log_as_watched(
    db: Database,
    item_id: int,
    *,
    watched_on: str | None = None,
    rating: int | None = None,
    liked: bool | None = None,
    keep_on_watchlist: bool = False,
) -> dict:
    card = require_card(db, item_id)
    entry_id = db.log_watch(
        item_id, watched_on or date.today().isoformat(), rating=rating, liked=liked
    )
    if not keep_on_watchlist and card["status"]["on_watchlist"]:
        db.set_watchlist(item_id, False)
    return {"entry": db.get_watch_entry_view(entry_id), "item": db.get_item_card(item_id)}


def decorate_cards(db: Database, cards: list[dict], *, with_remaining: bool = False) -> list[dict]:
    """Attach completion deltas, genres and overview to cards (batched)."""
    ids = [c["item_id"] for c in cards]
    deltas = coll.completion_deltas(db, ids, with_remaining=with_remaining)
    facts = item_facts(db, ids)
    out = []
    for c in cards:
        row = dict(c)
        row["completion"] = [asdict(d) for d in deltas[c["item_id"]]]
        row["_gain"] = coll.best_gain(deltas[c["item_id"]])  # sort key, removed before returning
        row.update(facts[c["item_id"]])
        out.append(row)
    return out


def watchlist_view(
    db: Database,
    *,
    sort: str = "impact",
    runtime_max: int | None = None,
    decade: int | None = None,
    q: str | None = None,
    ranker: str = DEFAULT_RANKER,
    limit: int = 100,
    offset: int = 0,
    taste_fn: Callable[[list[int], str], dict[int, float]] | None = None,
) -> dict:
    """The decorated, sorted, paged watchlist.

    ``taste_fn(candidate_ids, ranker)`` supplies taste scores for ``sort="taste"`` (the web layer
    passes its cache); ``TasteUnavailableError`` from it propagates.
    """
    if sort not in WATCHLIST_SORTS:
        raise InvalidInputError(f"Unknown sort: {sort}")
    db_sort = sort if sort in ("added", "runtime", "year", "title") else "added"
    total, cards = db.get_watchlist(runtime_max=runtime_max, decade=decade, q=q, sort=db_sort)
    rows = decorate_cards(db, cards)

    if sort == "taste":
        if taste_fn is None:
            raise InvalidInputError("Taste sorting needs a taste function")
        taste = taste_fn([r["item_id"] for r in rows], ranker)
        rows.sort(key=lambda r: -taste.get(r["item_id"], -1.0))
        for r in rows:
            s = taste.get(r["item_id"])
            r["taste"] = {"score": round(s, 4), "ranker": ranker} if s is not None else None
    elif sort == "impact":
        rows.sort(key=lambda r: (-r["_gain"], r["title"].lower()))

    page = rows[offset:offset + limit]
    for r in page:
        r.pop("_gain", None)
    return {"total": total, "summary": db.watchlist_summary(), "items": page}


# --- Collections and the Concierge ---


def _director_summary(d: coll.DirectorCompletion, *, with_films: bool) -> dict:
    out = {k: v for k, v in asdict(d).items() if k != "films"}
    if with_films:
        out["films"] = [asdict(f) for f in (d.films or [])]
    return out


def directors_view(
    db: Database,
    *,
    sort: str = "pct",
    status: str = "all",
    q: str | None = None,
    min_films: int = 2,
    limit: int = 50,
    offset: int = 0,
    include_films: bool = False,
) -> dict:
    allc = coll.director_completion(db, sort=sort, status=status, q=q, min_films=min_films)
    page = allc[offset:offset + limit]
    if include_films:
        coll.attach_films(db, page)
    return {
        "total": len(allc),
        "summary": coll.collection_summary(db, min_films=min_films),
        "items": [_director_summary(d, with_films=include_films) for d in page],
    }


def director_view(db: Database, person_id: int) -> dict:
    d = coll.director_detail(db, person_id)
    if d is None:
        raise NotFoundError("No such director")
    out = _director_summary(d, with_films=True)
    for f in out["films"]:
        f["after_pct"] = None if f["seen"] else coll.pct(d.seen + 1, d.total)
    return out


def concierge_suggestions(db: Database) -> dict:
    prompts = list(DEFAULT_PROMPTS)
    nearest = [d for d in coll.director_completion(db, sort="pct") if d.seen < d.total]
    if nearest:
        prompts.insert(2, f"What should I watch next from {nearest[0].name}?")
    return {"prompts": prompts[:5]}


def concierge_overview(db: Database) -> dict:
    """Numbers and the completion radar for the Concierge home screen."""
    _, _, log_summary = db.get_watch_log(limit=1)
    rated = log_summary["avg_rating"]  # half-star integers across logged viewings

    directors = coll.director_completion(db, sort="pct")
    top = [d for d in directors if d.seen < d.total][:3]
    coll.attach_films(db, top)  # films are only needed for the radar cards
    radar = []
    for d in top:
        unseen = [f for f in (d.films or []) if not f.seen]
        unseen.sort(key=lambda f: (f.runtime_min is None, f.runtime_min or 0, f.title))
        q = unseen[0] if unseen else None
        radar.append({
            "person_id": d.person_id, "name": d.name, "seen": d.seen, "total": d.total,
            "pct": d.pct,
            "quickest": None if q is None else {
                "item_id": q.item_id, "title": q.title, "year": q.year,
                "runtime_min": q.runtime_min, "on_watchlist": q.on_watchlist,
                "after_pct": coll.pct(d.seen + 1, d.total),
            },
        })
    closest = None
    if radar:
        first = radar[0]
        closest = {k: first[k] for k in ("person_id", "name", "pct", "seen", "total", "quickest")}
    return {
        "watchlist": db.watchlist_summary(),
        "log": {
            "count": log_summary["count"],
            "avg_rating": None if rated is None else round(rated / 2, 1),
        },
        "directors": {"tracked": len(directors)},
        "closest": closest,
        "radar": radar,
    }


def concierge_pick(
    db: Database,
    query: str,
    *,
    model: Any = None,
    scope: str = "unseen",
    limit: int = 5,
    generator_fn: Callable[[str, str], str] | None = None,
    taste_fn: Callable[[list[int]], dict[int, float]] | None = None,
    w_taste: float = 0.0,
    w_comp: float = 0.0,
) -> dict:
    return pick(
        db,
        query,
        model=model,
        scope=scope,
        limit=limit,
        generator_fn=generator_fn,
        taste_fn=taste_fn,
        w_taste=w_taste,
        w_comp=w_comp,
    )
