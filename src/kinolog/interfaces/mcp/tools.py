"""MCP tool definitions (names, descriptions and input schemas)."""

from __future__ import annotations

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
