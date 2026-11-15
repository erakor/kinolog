from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from kinolog import services
from kinolog.config import DEFAULT_RANKER
from kinolog.interfaces.web.deps import get_db, get_state
from kinolog.interfaces.web.schemas import ItemRef, WatchedBody
from kinolog.interfaces.web.state import AppState
from kinolog.store import Database
from kinolog.taste import TasteUnavailableError

router = APIRouter(prefix="/api/watchlist")


@router.get("")
def list_watchlist(
    sort: str = "impact",
    runtime_max: int | None = Query(None, ge=1, le=1000),
    decade: int | None = Query(None, ge=1880, le=2100),
    q: str | None = None,
    ranker: str = DEFAULT_RANKER,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
):
    try:
        view = services.watchlist_view(
            db,
            sort=sort,
            runtime_max=runtime_max,
            decade=decade,
            q=q,
            ranker=ranker,
            limit=limit,
            offset=offset,
            taste_fn=lambda ids, name: state.taste_cache.scores(state.db, ids, name),
        )
    except TasteUnavailableError as e:
        raise HTTPException(409, {"code": "taste_unavailable", "message": str(e)}) from e
    return {
        "total": view["total"],
        "taste_available": state.taste_available(),
        "summary": view["summary"],
        "items": view["items"],
    }


@router.post("")
def add_to_watchlist(
    body: ItemRef, state: AppState = Depends(get_state), db: Database = Depends(get_db)
):
    card = services.add_to_watchlist(db, body.item_id)
    state.invalidate()
    return card


@router.delete("/{item_id}")
def remove_from_watchlist(
    item_id: int, state: AppState = Depends(get_state), db: Database = Depends(get_db)
):
    card = services.remove_from_watchlist(db, item_id)
    state.invalidate()
    return card


@router.post("/{item_id}/watched")
def log_as_watched(
    item_id: int,
    body: WatchedBody,
    state: AppState = Depends(get_state),
    db: Database = Depends(get_db),
):
    result = services.log_as_watched(
        db,
        item_id,
        watched_on=body.watched_on,
        rating=body.rating,
        liked=body.liked,
        keep_on_watchlist=body.keep_on_watchlist,
    )
    state.invalidate()
    return result
