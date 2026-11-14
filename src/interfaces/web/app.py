"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from src.core.db import Database
from src.interfaces.web.state import AppState

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(
    db: Database | str = "data/index.db",
    *,
    load_model: bool = True,
    generator: Callable[[str, str], str] | None = None,
    llm_enabled: bool = False,
) -> FastAPI:
    if isinstance(db, str):
        db = Database(db, check_same_thread=False)

    app = FastAPI(title="Kinolog", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.kin = AppState(
        db, load_model=load_model, generator=generator, llm_enabled=llm_enabled
    )

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        """No CORS: reject cross-origin writes and non-JSON/multipart bodies."""
        if request.method in MUTATING:
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return error_response(403, "cross_origin", "Cross-origin writes are not allowed")
            ctype = request.headers.get("content-type", "")
            has_body = request.headers.get("content-length", "0") not in ("", "0")
            if has_body and not ctype.startswith(("application/json", "multipart/form-data")):
                return error_response(415, "unsupported_media_type", "Use application/json")
        return await call_next(request)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        code = exc.detail.get("code") if isinstance(exc.detail, dict) else None
        msg = exc.detail.get("message") if isinstance(exc.detail, dict) else str(exc.detail)
        return error_response(exc.status_code, code or f"http_{exc.status_code}", msg)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        return error_response(422, "invalid_request", f"{loc}: {first.get('msg', 'invalid')}")

    @app.exception_handler(KeyError)
    async def key_error(_: Request, exc: KeyError):
        return error_response(404, "not_found", str(exc.args[0]) if exc.args else "Not found")

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError):
        return error_response(422, "invalid_request", str(exc))

    from src.interfaces.web.routes import collections, health, items, log, watchlist

    app.include_router(health.router)
    app.include_router(collections.router)
    app.include_router(watchlist.router)
    app.include_router(items.router)
    app.include_router(log.router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
