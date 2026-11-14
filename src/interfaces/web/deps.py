"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, Request

from src.core.db import Database
from src.interfaces.web.state import AppState


def get_state(request: Request) -> AppState:
    return request.app.state.kin


def get_db(request: Request) -> Iterator[Database]:
    """Hold the DB lock for the duration of the request."""
    state: AppState = request.app.state.kin
    state.db_lock.acquire()
    try:
        yield state.db
    finally:
        state.db_lock.release()


def card_or_404(db: Database, item_id: int) -> dict:
    """The item's UI card, or a 404 in the API error shape."""
    card = db.get_item_card(item_id)
    if card is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No such item: {item_id}"})
    return card
