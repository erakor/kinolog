"""Tests for director completion."""

import pytest

from kinolog.features.collections import (
    collection_summary,
    completion_deltas,
    director_completion,
    director_detail,
)
from kinolog.store import Database


@pytest.fixture
def db():
    d = Database(":memory:")
    names = ["Ann", "Bob", "Cy"]
    people = {n: d.upsert_person(n, tmdb_person_id=i) for i, n in enumerate(names, 1)}

    def film(title, year, director, runtime=100, seen=False, liked=False, queued=False, **kw):
        i = d.upsert_item("film", title, year, runtime_min=runtime, **kw)
        d.upsert_credit(i, people[director], "Director", "Directing")
        d.upsert_user_status(i, seen=int(seen), liked=int(liked), on_watchlist=int(queued))
        return i

    film("A1", 1990, "Ann", seen=True, liked=True)
    film("A2", 1995, "Ann", seen=True)
    film("A3", 2000, "Ann", queued=True)
    film("A4", 2005, "Ann")
    film("A-short", 2001, "Ann", runtime=12)       # excluded: short
    film("A-tv", 2002, "Ann", runtime=90, is_tv=1)  # excluded: TV
    film("B1", 1980, "Bob", seen=True)
    film("B2", 1985, "Bob", seen=True)
    film("C1", 1970, "Cy", seen=True)               # single film: below min_films
    film("A-unk", 2010, "Ann", runtime=None)        # unknown runtime is counted
    d.upsert_item("book", "A Book", 2000)
    yield d
    d.close()


def test_completion_counts_and_exclusions(db):
    res = {d.name: d for d in director_completion(db)}
    assert set(res) == {"Ann", "Bob"}  # Cy has 1 film
    ann = res["Ann"]
    assert (ann.seen, ann.total) == (2, 5)  # A1-A4 + unknown runtime; short and TV excluded
    assert ann.pct == 40.0 and ann.hearted == 1 and ann.unseen_on_watchlist == 1
    assert res["Bob"].pct == 100.0


def test_sorts_and_status_filters(db):
    assert [d.name for d in director_completion(db, sort="pct")] == ["Bob", "Ann"]
    assert [d.name for d in director_completion(db, sort="name")] == ["Ann", "Bob"]
    assert [d.name for d in director_completion(db, sort="hearted")][0] == "Ann"
    # completed directors sort last under "remaining"
    assert [d.name for d in director_completion(db, sort="remaining")] == ["Ann", "Bob"]
    assert [d.name for d in director_completion(db, status="in_progress")] == ["Ann"]
    assert [d.name for d in director_completion(db, status="completed")] == ["Bob"]
    with pytest.raises(ValueError):
        director_completion(db, sort="nope")


def test_query_matches_director_or_film_title(db):
    assert [d.name for d in director_completion(db, q="bob")] == ["Bob"]
    assert [d.name for d in director_completion(db, q="a3")] == ["Ann"]


def test_with_films_and_detail_flags_unknown_runtime(db):
    ann = director_completion(db, with_films=True)[1]
    assert [f.title for f in ann.films][:2] == ["A1", "A2"]
    detail = director_detail(db, ann.person_id)
    unk = next(f for f in detail.films if f.title == "A-unk")
    assert unk.runtime_unknown is True
    assert director_detail(db, 9999) is None


def test_summary(db):
    assert collection_summary(db) == {"tracked": 2, "above_50": 1, "completed": 1}


def test_completion_deltas_batched(db):
    ids = {r["title"]: r["id"] for r in db.execute("SELECT id, title FROM items")}
    out = completion_deltas(
        db, [ids["A3"], ids["A1"], ids["A-short"], ids["A Book"]], with_remaining=True
    )
    assert out[ids["A3"]][0].before_pct == 40.0 and out[ids["A3"]][0].after_pct == 60.0
    assert {r["title"] for r in out[ids["A3"]][0].remaining} == {"A4", "A-unk"}
    assert out[ids["A1"]] == []        # already seen: no delta
    assert out[ids["A-short"]] == []   # excluded from collections
    assert out[ids["A Book"]] == []    # no credits
    assert completion_deltas(db, []) == {}


def test_delta_skips_single_film_directors(db):
    cy = db.execute("SELECT id FROM items WHERE title='C1'").fetchone()["id"]
    db.upsert_user_status(cy, seen=0)
    assert completion_deltas(db, [cy])[cy] == []
