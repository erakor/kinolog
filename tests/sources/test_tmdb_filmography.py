"""Filmography enricher: stub client, disk cache redirected to tmp_path, no network."""

import json

import pytest

from kinolog.sources.tmdb import client as tmdb_client
from kinolog.sources.tmdb.client import TMDBClient
from kinolog.sources.tmdb.filmography import (
    enrich_all_filmographies,
    enrich_director_filmography,
)

CREDITS = {
    "crew": [
        {"id": 1, "job": "Director", "title": "One", "release_date": "1990-01-01"},
        {"id": 2, "job": "Co-Director", "title": "Shared", "release_date": "1991-01-01"},
        {"id": 3, "job": "Director", "title": "Three", "release_date": "2001-03-04"},
        {"id": 4, "job": "Assistant Director", "title": "Nope"},
    ],
}
DETAILS = {
    1: {"title": "One", "release_date": "1990-01-01", "runtime": 100, "status": "Released",
        "genres": [{"id": 99, "name": "Documentary"}]},
    3: {"title": "Three", "release_date": "2001-03-04", "runtime": 0, "status": "Released",
        "video": True, "genres": [{"id": 18, "name": "Drama"}]},
}


class StubClient:
    def __init__(self, credits=None, details=None, fail_details=()):
        self.credits = credits if credits is not None else {}
        self.details = details if details is not None else DETAILS
        self.fail_details = set(fail_details)
        self.person_calls, self.detail_calls = [], []

    def get_person_movie_credits(self, tmdb_person_id, refresh=False):
        self.person_calls.append((tmdb_person_id, refresh))
        return self.credits.get(tmdb_person_id, CREDITS)

    def get_details(self, tmdb_id):
        self.detail_calls.append(tmdb_id)
        if tmdb_id in self.fail_details:
            raise RuntimeError("boom")
        return self.details[tmdb_id]


@pytest.fixture
def ann(db):
    return db.upsert_person("Ann", tmdb_person_id=77)


def rows(db, table):
    return [dict(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY 1, 2")]


def test_writes_director_rows_only(db, ann):
    res = enrich_director_filmography(db, StubClient(), ann)
    assert res["status"] == "success" and res["director_films"] == 2
    assert [r["tmdb_id"] for r in rows(db, "person_filmography")] == [1, 3]
    movies = {r["tmdb_id"]: r for r in rows(db, "tmdb_movies")}
    assert set(movies) == {1, 3}
    assert movies[1]["runtime"] == 100 and json.loads(movies[1]["genre_ids"]) == [99]
    assert movies[3]["runtime"] is None and movies[3]["is_video"] == 1  # runtime 0 -> NULL
    assert movies[3]["year"] == 2001 and movies[3]["status"] == "Released"


def test_second_run_is_idempotent(db, ann):
    enrich_director_filmography(db, StubClient(), ann)
    before = (rows(db, "tmdb_movies"), rows(db, "person_filmography"))
    enrich_director_filmography(db, StubClient(), ann)
    after = (rows(db, "tmdb_movies"), rows(db, "person_filmography"))
    assert [r["tmdb_id"] for r in after[0]] == [r["tmdb_id"] for r in before[0]]
    assert after[1] == before[1]


def test_records_raw_cache_entries(db, ann):
    enrich_director_filmography(db, StubClient(), ann)
    sources = {(r["source"], r["external_id"]) for r in db.execute("SELECT * FROM raw_cache")}
    assert ("tmdb_person_movie_credits", "77") in sources
    assert {("tmdb", "1"), ("tmdb", "3")} <= sources
    path = db.execute(
        "SELECT path FROM raw_cache WHERE source = 'tmdb_person_movie_credits'"
    ).fetchone()["path"]
    assert path.endswith("person_77_movie_credits.json")


def test_person_without_tmdb_id_is_skipped_and_counted(db):
    a = db.upsert_person("Ann", tmdb_person_id=77)
    b = db.upsert_person("NoId")
    for name, pid in (("A1", a), ("A2", a), ("B1", b), ("B2", b)):
        item = db.upsert_item("film", name, 2000)
        db.upsert_credit(item, pid, "Director", "Directing")
        db.upsert_user_status(item, seen=1)
    stats = enrich_all_filmographies(db, StubClient(), min_seen=2)
    assert (stats["total_directors"], stats["enriched"], stats["skipped_no_tmdb"]) == (2, 1, 1)
    assert enrich_director_filmography(db, StubClient(), b)["reason"] == "no_tmdb_person_id"


def test_min_seen_name_and_limit_select_directors(db):
    for n, tid, seen in (("Ann", 1, 3), ("Bob", 2, 2), ("Cy", 3, 1)):
        p = db.upsert_person(n, tmdb_person_id=tid)
        for k in range(seen):
            item = db.upsert_item("film", f"{n}{k}", 2000)
            db.upsert_credit(item, p, "Director", "Directing")
            db.upsert_user_status(item, seen=1)
    stub = StubClient()
    enrich_all_filmographies(db, stub, min_seen=2)
    assert {c[0] for c in stub.person_calls} == {1, 2}
    stub = StubClient()
    enrich_all_filmographies(db, stub, min_seen=2, limit=1)
    assert [c[0] for c in stub.person_calls] == [1]  # most seen first
    stub = StubClient()
    enrich_all_filmographies(db, stub, person_name="Cy")
    assert [c[0] for c in stub.person_calls] == [3]


def test_one_failing_details_fetch_does_not_abort_the_director(db, ann):
    res = enrich_director_filmography(db, StubClient(fail_details={1}), ann)
    assert res["director_films"] == 2 and res["detail_errors"] == 1
    movie = db.execute("SELECT * FROM tmdb_movies WHERE tmdb_id = 1").fetchone()
    assert movie["status"] is None  # unknown, so not counted as a feature until fetched


def test_no_details_mode_makes_no_detail_calls_and_uses_the_disk_cache(
    db, ann, tmp_path, monkeypatch
):
    monkeypatch.setattr(tmdb_client, "CACHE_DIR", tmp_path)
    (tmp_path / "movie_1.json").write_text(json.dumps(DETAILS[1]))
    stub = StubClient()
    enrich_director_filmography(db, stub, ann, fetch_details=False)
    assert stub.detail_calls == []
    movies = {r["tmdb_id"]: r for r in rows(db, "tmdb_movies")}
    assert movies[1]["status"] == "Released" and movies[1]["runtime"] == 100
    assert movies[3]["status"] is None


def test_client_reads_cached_person_credits_without_http(tmp_path, monkeypatch):
    monkeypatch.setattr(tmdb_client, "CACHE_DIR", tmp_path)
    (tmp_path / "person_77_movie_credits.json").write_text(json.dumps(CREDITS))
    client = TMDBClient(api_key="test")

    def no_http(*a, **k):
        raise AssertionError("network was used")

    monkeypatch.setattr(client, "_get", no_http)
    assert client.get_person_movie_credits(77) == CREDITS
    with pytest.raises(AssertionError):
        client.get_person_movie_credits(77, refresh=True)


def test_client_fetches_and_caches_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(tmdb_client, "CACHE_DIR", tmp_path)
    client = TMDBClient(api_key="test")
    calls = []
    monkeypatch.setattr(client, "_get", lambda path, **k: calls.append(path) or CREDITS)
    client.get_person_movie_credits(5)
    client.get_person_movie_credits(5)
    assert calls == ["/person/5/movie_credits"]
    assert (tmp_path / "person_5_movie_credits.json").exists()


def test_pipeline_step_wires_the_client_and_closes_it(db, ann, monkeypatch):
    from kinolog import pipeline

    stub = StubClient()
    stub.close = lambda: stub.__dict__.setdefault("closed", True)
    monkeypatch.setattr("kinolog.sources.tmdb.client.TMDBClient", lambda: stub)
    stats = pipeline.filmographies(db, person_name="Ann", refresh=True)
    assert stats["enriched"] == 1 and stub.closed
    assert stub.person_calls == [(77, True)]


def test_cli_filmographies_without_key_prints_hint(tmp_path, monkeypatch, capsys):
    from kinolog.interfaces.cli.ingest import handle_ingest_filmographies

    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    handle_ingest_filmographies(str(tmp_path / "x.db"))
    assert "TMDB_API_KEY not set" in capsys.readouterr().out
    assert not (tmp_path / "x.db").exists()


def test_cli_parser_accepts_filmographies_options():
    from kinolog.interfaces.cli.main import build_parser

    args = build_parser().parse_args(
        ["ingest", "filmographies", "--min-seen", "3", "--person", "Fellini", "--limit", "5",
         "--no-details", "--refresh", "--db", "x.db"]
    )
    assert (args.min_seen, args.person, args.limit) == (3, "Fellini", 5)
    assert args.no_details and args.refresh and args.db == "x.db"
