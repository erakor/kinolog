"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from kinolog.interfaces.web.state import AppState
from kinolog.store import Database


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

