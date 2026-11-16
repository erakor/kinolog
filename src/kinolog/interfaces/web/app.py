"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from kinolog.config import DEFAULT_DB_PATH
from kinolog.interfaces.web.state import AppState
from kinolog.store import Database, InvalidInputError, NotFoundError

logger = logging.getLogger(__name__)

DIST_DIR = Path(__file__).parent / "dist"
BUILD_HINT = (
    "pnpm -C frontend install --frozen-lockfile && "
    "pnpm -C frontend build"
)
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _hostname(host_header: str) -> str:
    """Host without port, IPv6 brackets removed."""
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host
    return host.split(":")[0]


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(
    db: Database | str = str(DEFAULT_DB_PATH),
    *,
    load_model: bool = True,
    generator: Callable[[str, str], str] | None = None,
    w_taste: float = 0.0,
    w_comp: float = 0.0,
    allowed_hosts: frozenset[str] | set[str] | None = None,
    dist_dir: Path | None = None,
) -> FastAPI:
    """``allowed_hosts`` are the Host header names accepted (default: loopback names only);
    {"*"} accepts any. Rejecting unknown Hosts stops DNS-rebinding pages from reaching the API.
    ``dist_dir`` is the built frontend (default: ``web/dist``)."""
    dist = DIST_DIR if dist_dir is None else Path(dist_dir)
    allowed = LOOPBACK_HOSTS if allowed_hosts is None else frozenset(allowed_hosts)
    if isinstance(db, str):
        db = Database(db, check_same_thread=False)

    app = FastAPI(title="Kinolog", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.kin = AppState(
        db, load_model=load_model, generator=generator, w_taste=w_taste, w_comp=w_comp,
    )

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        """Reject unknown Hosts, cross-origin writes and non-JSON/multipart bodies (no CORS)."""
        if "*" not in allowed and _hostname(request.headers.get("host", "")) not in allowed:
            return error_response(400, "bad_host", "Unexpected Host header")
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

    # Only the database layer's domain errors map to client errors; any other KeyError or
    # ValueError is a bug and must surface as a 500 with a logged traceback.
    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError):
        return error_response(404, "not_found", str(exc.args[0]) if exc.args else "Not found")

    @app.exception_handler(InvalidInputError)
    async def invalid_input(_: Request, exc: InvalidInputError):
        return error_response(422, "invalid_request", str(exc))

    from kinolog.interfaces.web.routes import (
        collections,
        concierge,
        health,
        imports,
        items,
        log,
        watchlist,
    )

    app.include_router(health.router)
    app.include_router(collections.router)
    app.include_router(watchlist.router)
    app.include_router(items.router)
    app.include_router(log.router)
    app.include_router(imports.router)
    app.include_router(concierge.router)

    # check_dir=False: the build may appear after the server starts
    app.mount("/assets", StaticFiles(directory=dist / "assets", check_dir=False), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        page = dist / "index.html"
        if page.is_file():
            return FileResponse(page)
        return HTMLResponse(
            "<!doctype html><title>Kinolog: UI not built</title>"
            "<h1>The web UI has not been built</h1>"
            "<p>Build it once (needs Node), then reload:</p>"
            f"<pre>{BUILD_HINT}</pre>",
            status_code=503,
        )

    return app
