"""Tests for MCP server tool handling."""

import pytest

from kinolog.index.chunking import chunk_document
from kinolog.interfaces.mcp.server import KinologServer
from kinolog.interfaces.mcp.tools import TOOLS
from kinolog.store import Database


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
    assert "director_completion" in tool_names
    assert "watchlist_by_director_impact" in tool_names


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


def test_rank_watchlist_uses_db_id_helpers(mcp_server, monkeypatch):
    from kinolog import taste

    seen_args = {}

    def fake_ranker(db, candidate_ids, heart_ids, **kw):
        seen_args["c"], seen_args["h"] = candidate_ids, heart_ids
        return [taste.TasteScore(item_id=i, score=1.0, method="fake") for i in candidate_ids]

    monkeypatch.setitem(taste.RANKERS, "nearest_exemplar", fake_ranker)
    out = mcp_server.handle_tool("rank_watchlist", {})
    assert seen_args["c"] == mcp_server.db.get_watchlist_ids()
    assert seen_args["h"] == mcp_server.db.get_heart_ids()
    assert out and out[0]["title"] == "Solaris"


def test_director_completion_lists_fellini_as_index_only(mcp_server):
    (row,) = mcp_server.handle_tool("director_completion", {})
    assert (row["person"], row["seen"], row["total"], row["percent"]) == (
        "Federico Fellini",
        2,
        2,
        100,
    )
    assert row["coverage"] == "index_only" and "films" not in row


def test_director_completion_with_a_name_returns_films(mcp_server):
    (row,) = mcp_server.handle_tool("director_completion", {"name": "Fellini"})
    assert [f["title"] for f in row["films"]] == ["La Dolce Vita", "8½"]
    assert all(f["seen"] and f["if_watched"] is None for f in row["films"])


def test_watchlist_by_director_impact_runs_with_max_runtime(mcp_server):
    assert mcp_server.handle_tool("watchlist_by_director_impact", {"max_runtime": 90}) == []
    db = mcp_server.db
    fellini = db.execute("SELECT id FROM people WHERE name = 'Federico Fellini'").fetchone()["id"]
    amarcord = db.upsert_item("film", "Amarcord", 1973, runtime_min=123)
    db.upsert_credit(amarcord, fellini, "Director", "Directing")
    db.upsert_user_status(amarcord, seen=0, on_watchlist=1)
    (hit,) = mcp_server.handle_tool("watchlist_by_director_impact", {"max_runtime": 130})
    assert hit["title"] == "Amarcord"
    d = hit["directors"][0]
    assert (d["before"], d["after"], d["completes"]) == ("2/3", "3/3", True)
    assert mcp_server.handle_tool("watchlist_by_director_impact", {"max_runtime": 100}) == []


def test_director_completion_tools_return_errors_for_bad_arguments(mcp_server):
    assert "error" in mcp_server.handle_tool("director_completion", {"limit": 0})
    assert "error" in mcp_server.handle_tool("director_completion", {"limit": "many"})
    assert "error" in mcp_server.handle_tool("watchlist_by_director_impact", {"max_runtime": -5})
