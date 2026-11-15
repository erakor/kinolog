"""TMDB resolver matching (against a fake client) and the on-disk cache contract."""

from kinolog.sources.http_cache import read_json, write_json
from kinolog.sources.tmdb import client as tmdb_client
from kinolog.sources.tmdb.resolve import TMDBResolver
from kinolog.store import Database


class FakeClient:
    def __init__(self, results):
        self.results = results
        self.closed = False

    def search(self, title, year=None, language="en-US"):
        return self.results if language == "en-US" else []

    def get_details(self, tmdb_id):
        return {"alternative_titles": {"titles": []}}

    def close(self):
        self.closed = True


def test_confident_match_is_stored_as_auto():
    db = Database(":memory:")
    item_id = db.upsert_item("film", "La Dolce Vita", 1960)
    client = FakeClient([{"id": 42, "title": "La Dolce Vita", "original_title": "La dolce vita",
                          "release_date": "1960-02-05", "popularity": 10}])
    result = TMDBResolver(client).resolve_item(db, item_id, "La Dolce Vita", 1960)
    assert result["id"] == 42
    item = db.get_item(item_id)
    assert item["tmdb_id"] == 42 and item["match_status"] == "auto"


def test_no_results_goes_to_the_review_queue():
    db = Database(":memory:")
    item_id = db.upsert_item("film", "Nothing Here", 2001)
    assert TMDBResolver(FakeClient([])).resolve_item(db, item_id, "Nothing Here", 2001) is None
    assert db.get_item(item_id)["match_status"] == "queued"
    assert [q["item_id"] for q in db.get_review_queue()] == [item_id]


def test_resolver_close_closes_the_client():
    client = FakeClient([])
    TMDBResolver(client).close()
    assert client.closed


def test_json_cache_roundtrip_keeps_unicode(tmp_path):
    path = tmp_path / "movie_1.json"
    write_json(path, {"title": "Le Mépris"})
    assert "Le Mépris" in path.read_text(encoding="utf-8")  # ensure_ascii=False
    assert read_json(path) == {"title": "Le Mépris"}


def test_tmdb_cache_location_is_unchanged():
    assert tmdb_client.CACHE_DIR.as_posix() == "data/cache/tmdb"
