"""Run the Kinolog web UI: python3 -m kinolog.interfaces.web [--db PATH] [--port N]."""

from __future__ import annotations

import argparse
import ipaddress
import logging
import sys

from kinolog.config import DEFAULT_DB_PATH

LOOPBACK_NAMES = {"localhost"}


def is_loopback(host: str) -> bool:
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kinolog-web", description="Kinolog web UI")
    p.add_argument("--db", default=str(DEFAULT_DB_PATH))
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-model", action="store_true", help="never load the embedding model")
    p.add_argument("--llm", action="store_true", help="use the Anthropic API for rationales")
    p.add_argument(
        "--allow-remote", action="store_true", help="allow a non-loopback host (no auth!)"
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    if not is_loopback(args.host):
        if not args.allow_remote:
            print(
                f"Refusing to bind {args.host}: the UI has no authentication. "
                "Use --allow-remote to override.",
                file=sys.stderr,
            )
            return 2
        print(f"WARNING: serving on {args.host} without authentication", file=sys.stderr)

    import uvicorn

    from kinolog.interfaces.web.app import create_app

    generator = None
    if args.llm:
        from kinolog.rag.llm import build_generator

        generator = build_generator()
        if generator is None:
            print("--llm requested but no usable Anthropic setup; using templates", file=sys.stderr)

    from kinolog.interfaces.web.app import BUILD_HINT, DIST_DIR

    if not (DIST_DIR / "index.html").is_file():
        print(
            "Web UI is not built; the API works but / will return 503. "
            f"Build it with:\n  {BUILD_HINT}",
            file=sys.stderr,
        )

    app = create_app(
        args.db, load_model=not args.no_model, generator=generator,
        allowed_hosts={"*"} if args.allow_remote else None,
    )
    log_level = "debug" if args.verbose else "warning"  # access log carries concierge queries
    uvicorn.run(app, host=args.host, port=args.port, log_level=log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
