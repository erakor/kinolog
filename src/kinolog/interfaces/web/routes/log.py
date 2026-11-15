from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from kinolog.interfaces.web.deps import card_or_404, get_db, get_state
from kinolog.interfaces.web.schemas import LogCreate, LogPatch
from kinolog.interfaces.web.state import AppState
from kinolog.store import Database

router = APIRouter(prefix="/api/log")


@router.get("")
def list_log(
    year: int | None = Query(None, ge=1880, le=2200),
    month: int | None = Query(None, ge=1, le=12),
    min_rating: int | None = Query(None, ge=1, le=10),
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    total, entries, summary = db.get_watch_log(
        year=year, month=month, min_rating=min_rating, q=q, limit=limit, offset=offset
    )
    return {"total": total, "entries": entries, "summary": summary}


@router.post("", status_code=201)
def create_entry(
    body: LogCreate, state: AppState = Depends(get_state), db: Database = Depends(get_db)
):
    card = card_or_404(db, body.item_id)
    entry_id = db.log_watch(
        body.item_id, body.watched_on, rating=body.rating, liked=body.liked, rewatch=body.rewatch
    )
    # a logged film is no longer queued
    if card["status"]["on_watchlist"]:
        db.set_watchlist(body.item_id, False)
    state.invalidate()
    return db.get_watch_entry_view(entry_id)


@router.patch("/{entry_id}")
def patch_entry(
    entry_id: int,
    body: LogPatch,
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
):
    db.update_watch(entry_id, **body.model_dump(exclude_unset=True))
    state.invalidate()
    return db.get_watch_entry_view(entry_id)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int, state: AppState = Depends(get_state), db: Database = Depends(get_db)
):
    db.delete_watch(entry_id)
    state.invalidate()
    return Response(status_code=204)
