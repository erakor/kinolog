from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.db import Database
from src.interfaces.web.deps import get_db, get_state
from src.interfaces.web.schemas import LikedBody, RatingBody
from src.interfaces.web.state import AppState

router = APIRouter(prefix="/api/items")


@router.get("/lookup")
def lookup(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(8, ge=1, le=25),
    db: Database = Depends(get_db),
):
    return db.find_items_by_title(q, limit=limit)


@router.get("/{item_id}")
def get_item(item_id: int, db: Database = Depends(get_db)):
    card = db.get_item_card(item_id)
    if card is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such item"})
    rows = db.execute(
        "SELECT DISTINCT source FROM documents WHERE item_id = ? ORDER BY source", (item_id,)
    ).fetchall()
    return {**card, "sources": [r["source"] for r in rows]}


@router.put("/{item_id}/rating")
def set_rating(
    item_id: int,
    body: RatingBody,
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
):
    if db.get_item(item_id) is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such item"})
    db.set_rating(item_id, body.rating)
    state.invalidate()
    return db.get_item_card(item_id)


@router.put("/{item_id}/liked")
def set_liked(
    item_id: int,
    body: LikedBody,
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
):
    if db.get_item(item_id) is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such item"})
    db.set_liked(item_id, body.liked)
    state.invalidate()  # hearts feed taste ranking
    return db.get_item_card(item_id)
