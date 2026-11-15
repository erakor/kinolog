from kinolog.features.docfacts import item_facts, parse_tmdb_text
from kinolog.sources.tmdb.enrich import _build_document_text
from kinolog.store import Database

DETAILS = {
    "title": "Okay", "original_title": "Okay", "release_date": "2017-06-01",
    "genres": [{"name": "Drama"}, {"name": "Adventure"}], "runtime": 100,
    "credits": {"crew": [], "cast": []}, "overview": "A girl crosses the world.",
}


def test_parse_real_document_text():
    facts = parse_tmdb_text(_build_document_text(DETAILS))
    assert facts["genres"] == ["Drama", "Adventure"]
    assert facts["overview"] == "A girl crosses the world."


def test_no_overview_returns_empty():
    assert parse_tmdb_text("Title\nRuntime: 5 minutes")["overview"] == ""


def test_item_facts_prefers_english():
    db = Database(":memory:")
    i = db.upsert_item("film", "Okay", 2017)
    db.upsert_document(i, "tmdb", "fr", "Okay\nGenres: Drame\n\nUne fille.")
    db.upsert_document(i, "tmdb", "en", _build_document_text(DETAILS))
    assert item_facts(db, [i])[i]["overview"] == "A girl crosses the world."
    assert item_facts(db, []) == {}
