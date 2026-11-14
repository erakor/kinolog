"""Tests for search functionality."""

import pytest

from src.core.db import Database
from src.core.chunkers import chunk_document
from src.core.search import search_bm25, SearchFilters


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
