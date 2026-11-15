"""Tests for the OMDb ratings enricher (mocked transport, no network)."""

import json

import httpx
import pytest

from src.core.db import Database
from src.ingest.enrichers.omdb import (
    OMDbClient,
    OMDbQuotaError,
    enrich_all,
    parse_ratings,
)
from src.ingest.enrichers.tmdb import backfill_imdb_ids, enrich_item, imdb_id_from_details

MATRIX = {
    "Title": "The Matrix", "Year": "1999", "Response": "True",
    "imdbRating": "8.7", "imdbVotes": "2,123,456", "Metascore": "73",
    "Ratings": [
        {"Source": "Internet Movie Database", "Value": "8.7/10"},
        {"Source": "Rotten Tomatoes", "Value": "83%"},
        {"Source": "Metacritic", "Value": "73/100"},
    ],
}
NOT_FOUND = {"Response": "False", "Error": "Incorrect IMDb ID."}
LIMIT = {"Response": "False", "Error": "Request limit reached!"}


def make_client(tmp_path, responses: dict[str, tuple[int, dict]]):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        imdb_id = request.url.params["i"]
        calls.append(imdb_id)
        status, body = responses.get(imdb_id, (200, MATRIX))
        return httpx.Response(status, json=body)

    client = OMDbClient(
        api_key="k", rate_limit=0, cache_dir=tmp_path / "omdb",
        transport=httpx.MockTransport(handler),
    )
    return client, calls


def add_film(db, title, imdb_id, tmdb_id):
    return db.upsert_item(
        "film", title, 1999, tmdb_id=tmdb_id, imdb_id=imdb_id, match_status="auto"
    )


def by_source(ratings):
    return {r["source"]: r for r in ratings}


def test_parse_ratings_normalizes_all_sources():
    r = by_source(parse_ratings(MATRIX))
    assert r["imdb"]["score"] == 87.0 and r["imdb"]["votes"] == 2123456
    assert r["rotten_tomatoes"]["score"] == 83.0 and r["rotten_tomatoes"]["votes"] is None
    assert r["metacritic"]["score"] == 73.0 and r["metacritic"]["raw"] == "73/100"


def test_parse_ratings_falls_back_to_top_level_and_skips_na():
    data = {"Response": "True", "imdbRating": "6.4", "imdbVotes": "N/A",
            "Metascore": "N/A", "Ratings": []}
    r = by_source(parse_ratings(data))
    assert set(r) == {"imdb"} and r["imdb"]["score"] == 64.0 and r["imdb"]["votes"] is None
    assert parse_ratings(NOT_FOUND) == []


def test_imdb_id_from_tmdb_details():
    assert imdb_id_from_details({"imdb_id": "tt0133093"}) == "tt0133093"
    assert imdb_id_from_details({"imdb_id": "", "external_ids": {"imdb_id": "tt0133093"}}) \
        == "tt0133093"
    assert imdb_id_from_details({"imdb_id": None}) is None


def test_tmdb_enrich_stores_imdb_id():
    class Resolver:
        def get_details(self, tmdb_id):
            return {"title": "The Matrix", "external_ids": {"imdb_id": "tt0133093"},
                    "credits": {}}

    db = Database(":memory:")
    i = db.upsert_item("film", "The Matrix", 1999, tmdb_id=603)
    enrich_item(db, Resolver(), i, languages=("en",))
    assert db.get_item(i)["imdb_id"] == "tt0133093"


def test_backfill_imdb_ids_from_tmdb_cache(tmp_path):
    (tmp_path / "movie_603.json").write_text(json.dumps({"imdb_id": "tt0133093"}))
    db = Database(":memory:")
    i = db.upsert_item("film", "The Matrix", 1999, tmdb_id=603)
    j = db.upsert_item("film", "Uncached", 2000, tmdb_id=999)
    assert backfill_imdb_ids(db, tmp_path)["imdb_ids"] == 1
    assert db.get_item(i)["imdb_id"] == "tt0133093" and db.get_item(j)["imdb_id"] is None


def test_enrich_all_stores_ratings_and_uses_cache(tmp_path):
    db = Database(":memory:")
    i = add_film(db, "The Matrix", "tt0133093", 603)
    gone = add_film(db, "Gone", "tt9999999", 1)
    client, calls = make_client(tmp_path, {"tt9999999": (200, NOT_FOUND)})

    stats = enrich_all(db, client)
    assert stats["rated"] == 1 and stats["not_found"] == 1 and stats["requests"] == 2
    assert by_source(db.get_external_ratings(i))["rotten_tomatoes"]["score"] == 83.0
    assert db.get_external_ratings(gone) == []

    again = enrich_all(db, client)  # rated film skipped; "not found" answer is cached
    assert again["requests"] == 0 and again["not_found"] == 1 and len(calls) == 2
    assert db.stats()["external_ratings"] == 3


def test_enrich_all_respects_request_cap_and_prioritizes_unrated(tmp_path):
    db = Database(":memory:")
    ids = [add_film(db, f"F{n}", f"tt100000{n}", n) for n in range(3)]
    client, _ = make_client(tmp_path, {})
    first = enrich_all(db, client, max_requests=2)
    assert first["requests"] == 2 and first["deferred"] == 1
    second = enrich_all(db, client, max_requests=1)
    assert second["requests"] == 1 and second["deferred"] == 0
    assert all(db.get_external_ratings(i) for i in ids)


def test_quota_error_stops_network_but_keeps_cached(tmp_path):
    db = Database(":memory:")
    a = add_film(db, "A", "tt1000001", 1)
    b = add_film(db, "B", "tt1000002", 2)
    c = add_film(db, "C", "tt1000003", 3)
    client, calls = make_client(tmp_path, {"tt1000002": (401, LIMIT)})
    stats = enrich_all(db, client)
    assert stats["quota_hit"] == 1 and stats["deferred"] == 2 and stats["errors"] == 0
    assert calls == ["tt1000001", "tt1000002"]  # C not attempted after the limit
    assert db.get_external_ratings(a) and not db.get_external_ratings(b)
    assert not db.get_external_ratings(c)
    assert not client.is_cached("tt1000002")  # the limit answer is never cached


def test_quota_error_raised_by_client(tmp_path):
    client, _ = make_client(tmp_path, {"tt1": (200, {"Response": "False",
                                                     "Error": "Invalid API key!"})})
    with pytest.raises(OMDbQuotaError):
        client.get_by_imdb_id("tt1")


def test_set_external_ratings_replaces_provider_rows():
    db = Database(":memory:")
    i = db.upsert_item("film", "X", 2000)
    db.set_external_ratings(i, "omdb", [{"source": "imdb", "score": 70},
                                        {"source": "metacritic", "score": 60}])
    db.set_external_ratings(i, "omdb", [{"source": "imdb", "score": 72, "votes": 10}])
    db.conn.commit()
    assert [(r["source"], r["score"], r["votes"]) for r in db.get_external_ratings(i)] \
        == [("imdb", 72.0, 10)]


def test_item_cards_include_external_ratings():
    db = Database(":memory:")
    i = db.upsert_item("film", "X", 2000)
    j = db.upsert_item("film", "Y", 2001)
    db.set_external_ratings(i, "omdb", [{"source": "imdb", "score": 81, "raw": "8.1/10",
                                         "votes": 5}])
    cards = db.get_item_cards([i, j])
    assert cards[i]["external_ratings"] == [
        {"source": "imdb", "score": 81.0, "raw": "8.1/10", "votes": 5}
    ]
    assert cards[j]["external_ratings"] == []
