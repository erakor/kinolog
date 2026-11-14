"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

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
