from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from kinolog.interfaces.web.deps import card_or_404, get_db, get_state
from kinolog.interfaces.web.schemas import LikedBody, RatingBody
from kinolog.interfaces.web.state import AppState
from kinolog.store import Database

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
    return {**card_or_404(db, item_id), "sources": db.get_item_sources(item_id)}


@router.put("/{item_id}/rating")
def set_rating(
    item_id: int,
    body: RatingBody,
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
):
    card_or_404(db, item_id)
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
    card_or_404(db, item_id)
    db.set_liked(item_id, body.liked)
    state.invalidate()  # hearts feed taste ranking
    return db.get_item_card(item_id)
