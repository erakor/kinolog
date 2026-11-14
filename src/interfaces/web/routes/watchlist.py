from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core import collections as coll
from src.core.db import Database
from src.core.docfacts import item_facts
from src.interfaces.web.deps import get_db, get_state
from src.interfaces.web.schemas import ItemRef, WatchedBody
from src.interfaces.web.state import AppState
from src.interfaces.web.taste import TasteUnavailableError, taste_scores

router = APIRouter(prefix="/api/watchlist")

SORTS = ("impact", "added", "runtime", "year", "title", "taste")


def decorate(db: Database, cards: list[dict], *, with_remaining: bool = False) -> list[dict]:
    """Attach completion deltas, genres and overview to cards (batched)."""
    ids = [c["item_id"] for c in cards]
    deltas = coll.completion_deltas(db, ids, with_remaining=with_remaining)
    facts = item_facts(db, ids)
    out = []
    for c in cards:
        row = dict(c)
        row["completion"] = [asdict(d) for d in deltas[c["item_id"]]]
        row.update(facts[c["item_id"]])
        out.append(row)
    return out


def _gain(row: dict) -> float:
    return max((d["after_pct"] - d["before_pct"] for d in row["completion"]), default=0.0)


@router.get("")
def list_watchlist(
    sort: str = "impact",
    runtime_max: int | None = Query(None, ge=1, le=1000),
    decade: int | None = Query(None, ge=1880, le=2100),
    q: str | None = None,
    ranker: str = "nearest_exemplar",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
):
    if sort not in SORTS:
        raise HTTPException(422, {"code": "invalid_request", "message": f"Unknown sort: {sort}"})
    db_sort = sort if sort in ("added", "runtime", "year", "title") else "added"
    total, cards = db.get_watchlist(runtime_max=runtime_max, decade=decade, q=q, sort=db_sort)
    rows = decorate(db, cards)

    taste = None
    if sort == "taste":
        try:
            taste = taste_scores(state, db, [r["item_id"] for r in rows], ranker)
        except TasteUnavailableError as e:
            raise HTTPException(409, {"code": "taste_unavailable", "message": str(e)}) from e
        rows.sort(key=lambda r: -taste.get(r["item_id"], -1.0))
        for r in rows:
            s = taste.get(r["item_id"])
            r["taste"] = {"score": round(s, 4), "ranker": ranker} if s is not None else None
    elif sort == "impact":
        rows.sort(key=lambda r: (-_gain(r), r["title"].lower()))

    _, all_cards = db.get_watchlist()
    minutes = sum(c["runtime_min"] or 0 for c in all_cards)
    return {
        "total": total,
        "taste_available": state.taste_available(db),
        "summary": {"count": len(all_cards), "total_minutes": minutes},
        "items": rows[offset:offset + limit],
    }


def _card_or_404(db: Database, item_id: int) -> dict:
    card = db.get_item_card(item_id)
    if card is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No such item: {item_id}"})
    return card


@router.post("")
def add_to_watchlist(
    body: ItemRef, state: AppState = Depends(get_state), db: Database = Depends(get_db)
):
    _card_or_404(db, body.item_id)
    db.set_watchlist(body.item_id, True)
    state.invalidate()
    return db.get_item_card(body.item_id)


@router.delete("/{item_id}")
def remove_from_watchlist(
    item_id: int, state: AppState = Depends(get_state), db: Database = Depends(get_db)
):
    _card_or_404(db, item_id)
    db.set_watchlist(item_id, False)
    state.invalidate()
    return db.get_item_card(item_id)


@router.post("/{item_id}/watched")
def log_as_watched(
    item_id: int,
    body: WatchedBody,
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
):
    card = _card_or_404(db, item_id)
    entry_id = db.log_watch(
        item_id, body.watched_on or date.today().isoformat(),
        rating=body.rating, liked=body.liked,
    )
    if not body.keep_on_watchlist and card["status"]["on_watchlist"]:
        db.set_watchlist(item_id, False)
    state.invalidate()
    return {"entry": db.get_watch_entry_view(entry_id), "item": db.get_item_card(item_id)}
