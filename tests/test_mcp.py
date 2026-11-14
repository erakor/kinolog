"""Tests for MCP server tool handling."""

import pytest

from src.core.chunkers import chunk_document
from src.core.db import Database
from src.interfaces.mcp_server import TOOLS, KinologServer


@pytest.fixture
def mcp_server(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(db_path)

    # Insert sample film data
    id1 = db.upsert_item("film", "La Dolce Vita", 1960)
    db.upsert_user_status(id1, seen=1, liked=1, on_watchlist=0)
    fellini = db.upsert_person("Federico Fellini", tmdb_person_id=4415)
    db.upsert_credit(id1, fellini, "Director", "Directing")

    doc1 = db.upsert_document(
        id1, "tmdb", "en", "A journalist in Rome experiencing decadence and modern society."
    )
    chunk_document(db, doc1, strategy="whole")

    id2 = db.upsert_item("film", "8½", 1963)
    db.upsert_user_status(id2, seen=1, liked=1, on_watchlist=0)
    db.upsert_credit(id2, fellini, "Director", "Directing")
    doc2 = db.upsert_document(
        id2, "tmdb", "en", "A film director suffers from creative blockage and artistic crisis."
    )
    chunk_document(db, doc2, strategy="whole")

    id3 = db.upsert_item("film", "Solaris", 1972)
    db.upsert_user_status(id3, seen=0, liked=0, on_watchlist=1)

    db.close()

    server = KinologServer(str(db_path))
    yield server
    server.db.close()


def test_tools_list():
    tool_names = [t["name"] for t in TOOLS]
    assert "search" in tool_names
    assert "rank_watchlist" in tool_names
    assert "similar_to" in tool_names
    assert "filmography" in tool_names
    assert "crew_overlap" in tool_names
    assert "stats" in tool_names


def test_stats_tool(mcp_server):
    result = mcp_server.handle_tool("stats", {})
    assert result["items"] == 3
    assert result["people"] == 1
    assert result["credits"] == 2


def test_search_tool_bm25(mcp_server):
    result = mcp_server.handle_tool("search", {"query": "Rome journalist", "mode": "bm25"})
    assert len(result) >= 1
    assert result[0]["title"] == "La Dolce Vita"


def test_filmography_tool(mcp_server):
    result = mcp_server.handle_tool("filmography", {"name": "Fellini"})
    assert len(result) >= 1
    entry = result[0]
    assert entry["person"] == "Federico Fellini"
    assert entry["seen"] == 2
    assert entry["total"] == 2


def test_crew_overlap_tool(mcp_server):
    result = mcp_server.handle_tool("crew_overlap", {"role": "Director", "min_overlap": 2})
    assert len(result) >= 1
    assert result[0]["person"] == "Federico Fellini"
    assert result[0]["heart_count"] == 2


def test_unknown_tool(mcp_server):
    result = mcp_server.handle_tool("nonexistent_tool", {})
    assert "error" in result
