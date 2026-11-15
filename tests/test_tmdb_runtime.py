"""Tests for runtime/TV extraction from TMDB data."""

from kinolog.ingest.enrichers.tmdb import (
    _build_document_text,
    backfill_runtime_and_tv,
    enrich_item,
    is_tv_movie,
)
from kinolog.store import Database

DETAILS = {
    "title": "Tiny", "original_title": "Tiny", "release_date": "1999-01-01",
    "genres": [{"name": "Drama"}, {"name": "TV Movie"}], "runtime": 74,
    "credits": {"crew": [], "cast": []}, "overview": "x",
}


class FakeResolver:
    def get_details(self, tmdb_id):
        return DETAILS


def test_is_tv_movie():
    assert is_tv_movie(["Drama", " tv movie "])
    assert not is_tv_movie(["Drama"])


def test_enrich_item_stores_runtime_and_tv():
    db = Database(":memory:")
    i = db.upsert_item("film", "Tiny", 1999, tmdb_id=5)
    enrich_item(db, FakeResolver(), i, languages=("en",))
    item = db.get_item(i)
    assert item["runtime_min"] == 74 and item["is_tv"] == 1


def test_backfill_from_documents_is_idempotent():
    db = Database(":memory:")
    i = db.upsert_item("film", "Tiny", 1999)
    j = db.upsert_item("film", "Plain", 2000)
    db.upsert_document(i, "tmdb", "en", _build_document_text(DETAILS))
    db.upsert_document(j, "tmdb", "en", "Plain (2000)\nGenres: Drama\nRuntime: 101 minutes\n")
    s1 = backfill_runtime_and_tv(db)
    assert s1["runtime"] == 2 and s1["tv"] == 1
    assert db.get_item(j)["runtime_min"] == 101 and db.get_item(j)["is_tv"] == 0
    s2 = backfill_runtime_and_tv(db)
    assert s2["runtime"] == 0
