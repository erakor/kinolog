"""Tests for TMDB filmography enricher."""

import json

import pytest

import src.ingest.enrichers.filmography as filmography_enricher_mod
import src.ingest.resolvers.tmdb as tmdb_resolver_mod
from src.core.db import Database
from src.ingest.enrichers.filmography import (
    enrich_all_filmographies,
    enrich_director_filmography,
)
from src.ingest.resolvers.tmdb import TMDBResolver


class StubTMDBResolver(TMDBResolver):
    """Stub resolver providing mock responses without making network requests."""

    def __init__(
        self,
        credits_map: dict[int, dict] | None = None,
        details_map: dict[int, dict] | None = None,
        fail_on_http: bool = False,
    ):
        self.credits_map = credits_map or {}
        self.details_map = details_map or {}
        self.fail_on_http = fail_on_http
        self.rate_limit = 0.0
        self._last_request = 0.0

    def _get(self, path: str, **params) -> dict:
        if self.fail_on_http:
            raise RuntimeError(f"Unexpected HTTP call to: {path}")

        if path.startswith("/person/") and path.endswith("/movie_credits"):
            person_id = int(path.split("/")[2])
            if person_id in self.credits_map:
                return self.credits_map[person_id]
        if path.startswith("/movie/"):
            movie_id = int(path.split("/")[2])
            if movie_id in self.details_map:
                return self.details_map[movie_id]
        return {}


@pytest.fixture
def patch_cache_dir(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache" / "tmdb"
    cache_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tmdb_resolver_mod, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(filmography_enricher_mod, "CACHE_DIR", cache_dir)
    return cache_dir


@pytest.fixture
def mem_db():
    db = Database(":memory:")
    yield db
    db.close()


# 19. Writes expected rows; only job == "Director" kept (Co-Director dropped).
def test_enrich_keeps_only_director(mem_db, patch_cache_dir):
    fellini = mem_db.upsert_person("Federico Fellini", tmdb_person_id=4415)
    credits_data = {
        "id": 4415,
        "crew": [
            {"id": 101, "job": "Director", "title": "8½", "release_date": "1963-02-14"},
            {
                "id": 102,
                "job": "Co-Director",
                "title": "Boccaccio '70",
                "release_date": "1962-02-22",
            },
            {
                "id": 103,
                "job": "Assistant Director",
                "title": "Paisan",
                "release_date": "1946-12-10",
            },
        ],
    }
    details_data = {
        101: {
            "id": 101,
            "title": "8½",
            "runtime": 138,
            "status": "Released",
            "genres": [{"id": 18, "name": "Drama"}],
        }
    }
    resolver = StubTMDBResolver(credits_map={4415: credits_data}, details_map=details_data)

    res = enrich_director_filmography(mem_db, resolver, fellini)
    assert res["status"] == "success"
    assert res["director_films"] == 1

    pf_rows = mem_db.execute(
        "SELECT * FROM person_filmography WHERE person_id = ?", (fellini,)
    ).fetchall()
    assert len(pf_rows) == 1
    assert pf_rows[0]["tmdb_id"] == 101
    assert pf_rows[0]["job"] == "Director"

    movie_row = mem_db.execute("SELECT * FROM tmdb_movies WHERE tmdb_id = 101").fetchone()
    assert movie_row is not None
    assert movie_row["title"] == "8½"
    assert movie_row["runtime"] == 138


# 20. Second run idempotent: same row counts, no duplicates.
def test_enrich_idempotent(mem_db, patch_cache_dir):
    fellini = mem_db.upsert_person("Federico Fellini", tmdb_person_id=4415)
    credits_data = {
        "id": 4415,
        "crew": [{"id": 101, "job": "Director", "title": "8½", "release_date": "1963-02-14"}],
    }
    details_data = {101: {"id": 101, "title": "8½", "runtime": 138, "status": "Released"}}
    resolver = StubTMDBResolver(credits_map={4415: credits_data}, details_map=details_data)

    enrich_director_filmography(mem_db, resolver, fellini)
    count_pf_1 = mem_db.execute("SELECT COUNT(*) FROM person_filmography").fetchone()[0]
    count_tm_1 = mem_db.execute("SELECT COUNT(*) FROM tmdb_movies").fetchone()[0]

    # Second run
    enrich_director_filmography(mem_db, resolver, fellini)
    count_pf_2 = mem_db.execute("SELECT COUNT(*) FROM person_filmography").fetchone()[0]
    count_tm_2 = mem_db.execute("SELECT COUNT(*) FROM tmdb_movies").fetchone()[0]

    assert count_pf_1 == count_pf_2 == 1
    assert count_tm_1 == count_tm_2 == 1


# 21. raw_cache row exists for tmdb_person_movie_credits.
def test_raw_cache_created(mem_db, patch_cache_dir):
    godard = mem_db.upsert_person("Jean-Luc Godard", tmdb_person_id=3776)
    credits_data = {
        "id": 3776,
        "crew": [
            {"id": 201, "job": "Director", "title": "Breathless", "release_date": "1960-03-16"}
        ],
    }
    resolver = StubTMDBResolver(credits_map={3776: credits_data})

    enrich_director_filmography(mem_db, resolver, godard, fetch_details=False)

    cache_row = mem_db.execute(
        """SELECT * FROM raw_cache
           WHERE source = 'tmdb_person_movie_credits' AND external_id = '3776'"""
    ).fetchone()
    assert cache_row is not None
    assert "person_3776_movie_credits.json" in cache_row["path"]


# 22. Person without tmdb_person_id skipped.
def test_skipped_without_tmdb_person_id(mem_db, patch_cache_dir):
    unknown_person = mem_db.upsert_person("Unknown Director", tmdb_person_id=None)
    resolver = StubTMDBResolver()

    res = enrich_director_filmography(mem_db, resolver, unknown_person)
    assert res["status"] == "skipped"
    assert res["reason"] == "no_tmdb_person_id"

    # Also skipped in enrich_all_filmographies
    item_id = mem_db.upsert_item("film", "Unknown Film", 2020)
    mem_db.upsert_credit(item_id, unknown_person, "Director", "Directing")
    mem_db.upsert_user_status(item_id, seen=1)

    stats = enrich_all_filmographies(mem_db, resolver, min_seen=1)
    assert stats["skipped_no_tmdb"] == 1
    assert stats["enriched"] == 0


# 23. Pre-written cache JSON read with no HTTP call (stub client raises if called).
def test_cache_hit_skips_http(mem_db, patch_cache_dir):
    fellini = mem_db.upsert_person("Federico Fellini", tmdb_person_id=4415)

    # Pre-write cache JSON files
    credits_file = patch_cache_dir / "person_4415_movie_credits.json"
    credits_file.write_text(
        json.dumps(
            {
                "id": 4415,
                "crew": [
                    {
                        "id": 301,
                        "job": "Director",
                        "title": "Cached Film",
                        "release_date": "1970-01-01",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    movie_file = patch_cache_dir / "movie_301.json"
    movie_file.write_text(
        json.dumps(
            {
                "id": 301,
                "title": "Cached Film",
                "runtime": 110,
                "status": "Released",
                "genres": [],
            }
        ),
        encoding="utf-8",
    )

    # Resolver that fails if any HTTP call is made
    resolver = StubTMDBResolver(fail_on_http=True)

    res = enrich_director_filmography(mem_db, resolver, fellini, fetch_details=True)
    assert res["status"] == "success"
    assert res["director_films"] == 1

    row = mem_db.execute("SELECT * FROM tmdb_movies WHERE tmdb_id = 301").fetchone()
    assert row is not None
    assert row["title"] == "Cached Film"
    assert row["runtime"] == 110
