"""Tests for search functionality."""

import pytest

from kinolog.index.chunking import chunk_document
from kinolog.retrieval import SearchFilters, search_bm25
from kinolog.store import Database


@pytest.fixture
def db_with_data():
    """Database with some test data for search."""
    db = Database(":memory:")

    # Add some films
    films = [
        ("La Dolce Vita", 1960, "Directed by: Federico Fellini. A film about modern Roman society and decadence."),
        ("8½", 1963, "Directed by: Federico Fellini. A filmmaker struggles with creative crisis and memories."),
        ("Le Mépris", 1963, "Directed by: Jean-Luc Godard. A couple's relationship disintegrates during a film production in Capri."),
        ("À bout de souffle", 1960, "Directed by: Jean-Luc Godard. A small-time thief steals a car and kills a policeman in Paris."),
        ("Bicycle Thieves", 1948, "Directed by: Vittorio De Sica. A man searches Rome for his stolen bicycle."),
    ]

    for title, year, text in films:
        item_id = db.upsert_item("film", title, year)
        db.upsert_user_status(item_id, seen=1)
        doc_id = db.upsert_document(item_id, "tmdb", "en", text)
        chunk_document(db, doc_id, strategy="whole")

    yield db
    db.close()


def test_bm25_search(db_with_data):
    results = search_bm25(db_with_data, "Fellini creative crisis")
    assert len(results) > 0
    # 8½ should rank high for "creative crisis"
    titles = [r.title for r in results]
    assert "8½" in titles


def test_bm25_search_with_filters(db_with_data):
    filters = SearchFilters(year_min=1960)
    results = search_bm25(db_with_data, "Fellini", filters=filters)
    # Bicycle Thieves (1948) should be excluded
    years = [r.year for r in results]
    assert all(y >= 1960 for y in years if y)


def test_bm25_search_empty_results(db_with_data):
    results = search_bm25(db_with_data, "xyznonexistent123")
    assert len(results) == 0


def test_bm25_search_director(db_with_data):
    results = search_bm25(db_with_data, "Godard")
    assert len(results) >= 2
    titles = {r.title for r in results}
    assert "Le Mépris" in titles
    assert "À bout de souffle" in titles


def test_runtime_and_id_filters(db_with_data):
    db = db_with_data
    runtimes = {"La Dolce Vita": 174, "8½": 138, "Le Mépris": 103, "À bout de souffle": 90}
    for title, rt in runtimes.items():
        db.execute("UPDATE items SET runtime_min = ? WHERE title = ?", (rt, title))
    # Bicycle Thieves keeps unknown runtime
    q = "Fellini Godard Rome film"
    all_titles = {r.title for r in search_bm25(db, q, limit=20)}
    assert "Bicycle Thieves" in all_titles

    short = search_bm25(db, q, limit=20, filters=SearchFilters(runtime_max=110))
    assert {r.title for r in short} == {"Le Mépris", "À bout de souffle"}  # unknown excluded

    long = search_bm25(db, q, limit=20, filters=SearchFilters(runtime_min=130))
    assert {r.title for r in long} == {"La Dolce Vita", "8½"}

    ids = [r.item_id for r in search_bm25(db, q, limit=20) if r.title == "8½"]
    only = search_bm25(db, q, limit=20, filters=SearchFilters(item_ids=ids))
    assert {r.title for r in only} == {"8½"}
    assert search_bm25(db, q, filters=SearchFilters(item_ids=[])) == []
    excl = search_bm25(db, q, limit=20, filters=SearchFilters(exclude_ids=ids))
    assert "8½" not in {r.title for r in excl}


def test_features_only_filter(db_with_data):
    db = db_with_data
    db.execute("UPDATE items SET runtime_min = 12 WHERE title = '8½'")
    db.execute("UPDATE items SET is_tv = 1 WHERE title = 'Bicycle Thieves'")
    q = "Fellini Godard Rome film"
    flt = SearchFilters(features_only=True)
    titles = {r.title for r in search_bm25(db, q, limit=20, filters=flt)}
    assert "8½" not in titles and "Bicycle Thieves" not in titles
    assert "La Dolce Vita" in titles
