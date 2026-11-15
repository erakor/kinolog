"""MCP server for Kinolog: tool dispatch over the shared services, plus the MCP app factory."""

from __future__ import annotations

import json
import logging
from typing import Any

from kinolog import services
from kinolog.config import DEFAULT_DB_PATH, DEFAULT_RANKER
from kinolog.interfaces.mcp.tools import TOOLS
from kinolog.store import Database, InvalidInputError, NotFoundError

logger = logging.getLogger(__name__)


class KinologServer:
    """MCP tool handler for Kinolog. Testable without the ``mcp`` package."""

    def __init__(self, db_path: str = str(DEFAULT_DB_PATH)):
        self.db = Database(db_path)
        self._model = None  # Lazy-loaded embedding model

    def _get_model(self):
        if self._model is None:
            try:
                from kinolog.index.embedding import BGE_M3
                self._model = BGE_M3()
            except Exception as e:
                logger.warning("Embedding model not available: %s", e)
        return self._model

    def handle_tool(self, name: str, args: dict) -> Any:
        """Dispatch a tool call."""
        if name == "search":
            return self._search(args)
        elif name == "rank_watchlist":
            return self._rank_watchlist(args)
        elif name == "similar_to":
            return self._similar_to(args)
        elif name == "filmography":
            return self._filmography(args)
        elif name == "crew_overlap":
            return self._crew_overlap(args)
        elif name == "director_completion":
            return self._director_completion(args)
        elif name == "watchlist_by_director_impact":
            return self._watchlist_by_director_impact(args)
        elif name == "stats":
            return self._stats(args)
        else:
            return {"error": f"Unknown tool: {name}"}

    def _search(self, args: dict) -> list[dict]:
        return services.search_items(
            self.db,
            args["query"],
            get_model=self._get_model,
            mode=args.get("mode", "rrf"),
            limit=args.get("limit", 10),
            item_type=args.get("item_type"),
            seen=args.get("seen"),
            decade=args.get("decade"),
        )

    def _rank_watchlist(self, args: dict) -> list[dict]:
        try:
            return services.rank_watchlist(
                self.db, args.get("ranker", DEFAULT_RANKER), args.get("limit", 20)
            )
        except InvalidInputError as e:
            return [{"error": str(e)}]

    def _similar_to(self, args: dict) -> list[dict]:
        try:
            return services.similar_to(
                self.db,
                args["title"],
                get_model=self._get_model,
                item_type=args.get("item_type"),
                limit=args.get("limit", 10),
            )
        except NotFoundError as e:
            return [{"error": e.args[0]}]
        except services.UnavailableError as e:
            return [{"error": str(e)}]

    def _filmography(self, args: dict) -> list[dict]:
        return services.filmography(self.db, args["name"], role=args.get("role"))

    def _crew_overlap(self, args: dict) -> list[dict]:
        return services.crew_overlap(
            self.db, role=args.get("role", "Director"), min_overlap=args.get("min_overlap", 2)
        )

    def _director_completion(self, args: dict) -> Any:
        try:
            return services.filmography_completion(
                self.db,
                name=args.get("name"),
                min_seen=args.get("min_seen"),
                min_total=args.get("min_total"),
                limit=args.get("limit", 25),
            )
        except (InvalidInputError, TypeError, ValueError) as e:
            return {"error": str(e)}

    def _watchlist_by_director_impact(self, args: dict) -> Any:
        try:
            return services.watchlist_director_impact(
                self.db,
                max_runtime=args.get("max_runtime"),
                include_unseen=bool(args.get("include_unseen", False)),
                include_unknown_runtime=bool(args.get("include_unknown_runtime", False)),
                limit=args.get("limit", 20),
            )
        except (InvalidInputError, TypeError, ValueError) as e:
            return {"error": str(e)}

    def _stats(self, args: dict) -> dict:
        return services.stats(self.db)


def create_mcp_app(db_path: str = str(DEFAULT_DB_PATH)):
    """Create an MCP-compatible server application."""
    try:
        from mcp.server import Server
        from mcp.types import TextContent, Tool
    except ImportError:
        logger.error("MCP library not installed. Install with: pip install 'kinolog[mcp]'")
        raise

    server = Server("kinolog")
    handler = KinologServer(db_path)

    @server.list_tools()
    async def list_tools():
        return [Tool(**t) for t in TOOLS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        result = handler.handle_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    return server
