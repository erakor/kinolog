"""MCP server for Kinolog — exposes search, rank_watchlist, and similar_to."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tool definitions for MCP
TOOLS = [
    {
        "name": "search",
        "description": "Search the film and book index. Supports BM25 (keyword), vector (semantic), and RRF (hybrid) search modes. Returns ranked results with titles, years, scores, and text snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query text",
                },
                "mode": {
                    "type": "string",
                    "enum": ["bm25", "vector", "rrf"],
                    "default": "rrf",
                    "description": "Search mode: bm25 (keyword), vector (semantic), rrf (hybrid)",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of results",
                },
                "item_type": {
                    "type": "string",
                    "enum": ["film", "book"],
                    "description": "Filter by item type",
                },
                "seen": {
                    "type": "boolean",
                    "description": "Filter by seen status",
                },
                "decade": {
                    "type": "integer",
                    "description": "Filter by decade (e.g., 1960)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "rank_watchlist",
        "description": "Rank watchlist films by taste affinity based on hearted films. Uses embedding-based taste rankers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ranker": {
                    "type": "string",
                    "enum": ["mean_heart", "nearest_exemplar", "top_3_mean", "prototypes_5"],
                    "default": "nearest_exemplar",
                    "description": "Taste ranking method",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum number of results",
                },
            },
        },
    },
    {
        "name": "similar_to",
        "description": "Find items similar to a given title using vector similarity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title to find similar items for",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "description": "Maximum number of results",
                },
                "item_type": {
                    "type": "string",
                    "enum": ["film", "book"],
                    "description": "Filter by item type",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "filmography",
        "description": "Show a person's filmography with seen/unseen status. Search by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Person's name (partial match supported)",
                },
                "role": {
                    "type": "string",
                    "description": "Filter by role (e.g., Director, Writer)",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "crew_overlap",
        "description": "Find crew members who appear in multiple hearted films. Useful for discovering auteur patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "default": "Director",
                    "description": "Role to check (Director, Writer, etc.)",
                },
                "min_overlap": {
                    "type": "integer",
                    "default": 2,
                    "description": "Minimum number of hearted films",
                },
            },
        },
    },
    {
        "name": "stats",
        "description": "Show database statistics: item counts, match status, review queue size.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]


class KinologServer:
    """MCP tool handler for Kinolog."""

    def __init__(self, db_path: str = "data/index.db"):
        from kinolog.core.db import Database
        self.db = Database(db_path)
        self._model = None  # Lazy-loaded embedding model

    def _get_model(self):
        if self._model is None:
            try:
                from kinolog.core.embed import BGE_M3
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
        elif name == "stats":
            return self._stats(args)
        else:
            return {"error": f"Unknown tool: {name}"}

    def _search(self, args: dict) -> list[dict]:
        from kinolog.core.search import SearchFilters, search

        filters = SearchFilters(
            item_type=args.get("item_type"),
            seen=args.get("seen"),
            decade=args.get("decade"),
        )

        mode = args.get("mode", "rrf")
        model = self._get_model() if mode in ("vector", "rrf") else None
        if model is None and mode != "bm25":
            mode = "bm25"

        results = search(
            self.db,
            args["query"],
            model=model,
            mode=mode,
            limit=args.get("limit", 10),
            filters=filters,
        )

        return [
            {
                "title": r.title,
                "year": r.year,
                "score": round(r.score, 4),
                "source": r.source,
                "snippet": r.chunk_text[:200] if r.chunk_text else "",
            }
            for r in results
        ]

    def _rank_watchlist(self, args: dict) -> list[dict]:
        try:
            from kinolog.core.taste import RANKERS
        except ImportError as e:
            return [{"error": f"Taste rankers unavailable: {e}"}]

        ranker_name = args.get("ranker", "nearest_exemplar")
        rank_fn = RANKERS.get(ranker_name)
        if not rank_fn:
            return [{"error": f"Unknown ranker: {ranker_name}"}]

        candidate_ids = self.db.get_watchlist_ids()
        heart_ids = self.db.get_heart_ids()

        scores = rank_fn(self.db, candidate_ids, heart_ids)
        limit = args.get("limit", 20)

        # Enrich with titles
        results = []
        for s in scores[:limit]:
            item = self.db.get_item(s.item_id)
            if item:
                results.append({
                    "title": item["title"],
                    "year": item["year"],
                    "score": round(s.score, 4),
                    "method": s.method,
                })

        return results

    def _similar_to(self, args: dict) -> list[dict]:
        from kinolog.core.search import SearchFilters, search_vector

        title = args["title"]
        item = self.db.execute(
            "SELECT id FROM items WHERE title LIKE ?", (f"%{title}%",)
        ).fetchone()

        if not item:
            return [{"error": f"Item not found: {title}"}]

        model = self._get_model()
        if model is None:
            return [{"error": "Embedding model not available"}]

        # Get the item's embedding
        vec_table = f"vec_{model.name}"
        row = self.db.execute(
            f"""SELECT v.embedding FROM {vec_table} v
                JOIN chunks c ON v.chunk_id = c.id
                WHERE c.item_id = ? LIMIT 1""",
            (item["id"],),
        ).fetchone()

        if not row:
            return [{"error": f"No embedding found for: {title}"}]

        try:
            import numpy as np
            query_embedding = np.frombuffer(row["embedding"], dtype=np.float32)
        except ImportError:
            return [{"error": "numpy is required for vector operations"}]

        filters = SearchFilters(item_type=args.get("item_type"))
        results = search_vector(
            self.db, query_embedding, model.name,
            limit=args.get("limit", 10) + 1, filters=filters,
        )

        # Exclude the query item itself
        return [
            {
                "title": r.title,
                "year": r.year,
                "score": round(r.score, 4),
            }
            for r in results if r.item_id != item["id"]
        ][:args.get("limit", 10)]

    def _filmography(self, args: dict) -> list[dict]:
        from kinolog.core.crew import filmography

        entries = filmography(self.db, person_name=args["name"], role=args.get("role"))
        results = []
        for entry in entries:
            results.append({
                "person": entry.person_name,
                "role": entry.role,
                "seen": entry.total_seen,
                "total": entry.total_in_db,
                "films": [
                    {"title": f["title"], "year": f.get("year"), "seen": bool(f["seen"])}
                    for f in entry.films
                ],
            })
        return results

    def _crew_overlap(self, args: dict) -> list[dict]:
        from kinolog.core.crew import crew_overlap_with_hearts

        results = crew_overlap_with_hearts(
            self.db,
            role=args.get("role", "Director"),
            min_overlap=args.get("min_overlap", 2),
        )
        return [
            {
                "person": r.person_name,
                "role": r.role,
                "heart_count": r.overlap_count,
                "seen_count": r.total_seen,
                "films": [f["title"] for f in r.films],
            }
            for r in results
        ]

    def _stats(self, args: dict) -> dict:
        s = self.db.stats()
        queue = self.db.get_review_queue()
        matched = self.db.execute(
            "SELECT COUNT(*) as c FROM items WHERE tmdb_id IS NOT NULL"
        ).fetchone()

        s["review_queue"] = len(queue)
        s["items_matched"] = matched["c"]
        return s


def create_mcp_app(db_path: str = "data/index.db"):
    """Create an MCP-compatible server application."""
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent
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


if __name__ == "__main__":
    import asyncio
    from mcp.server.stdio import stdio_server

    async def main():
        server = create_mcp_app()
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    asyncio.run(main())
