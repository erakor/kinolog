from __future__ import annotations

from fastapi import APIRouter, Depends

from src.core import collections as coll
from src.core.concierge import parse_constraints, pick
from src.core.db import Database
from src.interfaces.web.deps import get_db, get_state
from src.interfaces.web.schemas import ConciergeBody, ParseBody
from src.interfaces.web.state import AppState
from src.interfaces.web.taste import taste_scores

router = APIRouter(prefix="/api/concierge")

DEFAULT_PROMPTS = [
    "I have 90 minutes. Give me a movie.",
    "Help me finish a director I am close to completing",
    "Something tense and sharp under 2 hours",
    "A quiet comfort film from my watch list",
]


@router.get("/suggestions")
def suggestions(db: Database = Depends(get_db)):
    prompts = list(DEFAULT_PROMPTS)
    nearest = [d for d in coll.director_completion(db, sort="pct") if d.seen < d.total]
    if nearest:
        prompts.insert(2, f"What should I watch next from {nearest[0].name}?")
    return {"prompts": prompts[:5]}


@router.post("/parse")
def parse(body: ParseBody):
    return parse_constraints(body.query).to_dict()


@router.get("/overview")
def overview(db: Database = Depends(get_db)):
    """Numbers and the completion radar for the Concierge home screen."""
    _, queue = db.get_watchlist()
    minutes = sum(c["runtime_min"] or 0 for c in queue)
    _, _, log_summary = db.get_watch_log(limit=1)
    rated = log_summary["avg_rating"]  # half-star integers across logged viewings

    directors = coll.director_completion(db, sort="pct", with_films=True)
    incomplete = [d for d in directors if d.seen < d.total]
    radar = []
    for d in incomplete[:3]:
        unseen = [f for f in (d.films or []) if not f.seen]
        unseen.sort(key=lambda f: (f.runtime_min is None, f.runtime_min or 0, f.title))
        q = unseen[0] if unseen else None
        radar.append({
            "person_id": d.person_id, "name": d.name, "seen": d.seen, "total": d.total,
            "pct": d.pct,
            "quickest": None if q is None else {
                "item_id": q.item_id, "title": q.title, "year": q.year,
                "runtime_min": q.runtime_min, "on_watchlist": q.on_watchlist,
                "after_pct": round(100.0 * (d.seen + 1) / d.total, 1),
            },
        })
    closest = None
    if radar:
        top = radar[0]
        closest = {k: top[k] for k in ("person_id", "name", "pct", "seen", "total", "quickest")}
    return {
        "watchlist": {
            "count": len(queue),
            "total_minutes": minutes,
            "short_count": sum(1 for c in queue if c["runtime_min"] and c["runtime_min"] <= 90),
        },
        "log": {
            "count": log_summary["count"],
            "avg_rating": None if rated is None else round(rated / 2, 1),
        },
        "directors": {"tracked": len(directors)},
        "closest": closest,
        "radar": radar,
    }


@router.post("")
def concierge(body: ConciergeBody, state: AppState = Depends(get_state)):
    # Load the model (slow, first time only) before taking the DB lock.
    model = state.get_model() if state.db.vec_available else None
    with state.use_db() as db:
        result = pick(
            db,
            body.query,
            model=model,
            scope=body.scope,
            limit=body.limit,
            generator_fn=state.generator,
            taste_fn=lambda ids: taste_scores(state, db, ids),
            w_taste=state.w_taste,
            w_comp=state.w_comp,
        )
    result["degraded"] = list(dict.fromkeys(result["degraded"]))
    return result

