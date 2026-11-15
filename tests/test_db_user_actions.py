"""Tests for UI mutation and query methods on Database."""

import pytest

from kinolog.core.db import Database


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


def _film(db, title="Film", year=2000, runtime=100, director=None):
    i = db.upsert_item("film", title, year, runtime_min=runtime)
    if director:
        p = db.upsert_person(director)
        db.upsert_credit(i, p, "Director", "Directing")
    return i


def test_watchlist_add_remove(db):
    i = _film(db)
    db.set_watchlist(i, True)
    assert db.get_watchlist_ids() == [i]
    db.set_watchlist(i, False)
    assert db.get_watchlist_ids() == []
    row = db.execute("SELECT * FROM user_status WHERE item_id = ?", (i,)).fetchone()
    assert row["watchlist_removed_at"] and row["manual_updated_at"]
    db.set_watchlist(i, True)
    row = db.execute("SELECT * FROM user_status WHERE item_id = ?", (i,)).fetchone()
    assert row["watchlist_removed_at"] is None


def test_unknown_item_raises(db):
    with pytest.raises(KeyError):
        db.set_watchlist(999, True)


def test_log_watch_sets_seen_and_max_date(db):
    i = _film(db)
    db.log_watch(i, "2024-05-01")
    db.log_watch(i, "2023-01-01", rewatch=True)
    row = db.execute("SELECT seen, seen_date FROM user_status WHERE item_id = ?", (i,)).fetchone()
    assert row["seen"] == 1 and row["seen_date"] == "2024-05-01"


def test_delete_watch_tombstones_and_unsees(db):
    i = _film(db)
    e = db.log_watch(i, "2024-05-01")
    db.delete_watch(e)
    row = db.execute("SELECT seen FROM user_status WHERE item_id = ?", (i,)).fetchone()
    assert row["seen"] == 0
    assert db.get_watch_entry(e)["deleted_at"]
    assert db.get_watch_log()[0] == 0


def test_delete_one_of_two_keeps_seen_with_latest(db):
    i = _film(db)
    db.log_watch(i, "2022-01-01")
    e2 = db.log_watch(i, "2024-01-01")
    db.delete_watch(e2)
    row = db.execute("SELECT seen, seen_date FROM user_status WHERE item_id = ?", (i,)).fetchone()
    assert row["seen"] == 1 and row["seen_date"] == "2022-01-01"


def test_rating_validation(db):
    i = _film(db)
    for bad in (0, 11, 4.5, True):
        with pytest.raises(ValueError):
            db.set_rating(i, bad)
    db.set_rating(i, 9)
    assert db.get_item_card(i)["status"]["rating"] == 9
    db.set_rating(i, None)
    assert db.get_item_card(i)["status"]["rating"] is None


def test_bad_date_rejected(db):
    i = _film(db)
    with pytest.raises(ValueError):
        db.log_watch(i, "05/01/2024")


def test_set_liked_dates(db):
    i = _film(db)
    db.set_liked(i, True, at="2024-02-02")
    row = db.execute("SELECT liked, liked_date FROM user_status WHERE item_id = ?", (i,)).fetchone()
    assert row["liked"] == 1 and row["liked_date"] == "2024-02-02"
    db.set_liked(i, False)
    assert db.get_heart_ids() == []


def test_log_watch_idempotent_by_source_key(db):
    i = _film(db)
    a = db.log_watch(i, "2024-05-01", rating=8, source="letterboxd", source_key="k1")
    b = db.log_watch(i, "2024-05-01", rating=9, source="letterboxd", source_key="k1")
    assert a == b
    assert db.get_watch_entry(a)["rating"] == 9
    assert db.get_watch_log()[0] == 1


def test_tombstone_blocks_reimport_and_edit_blocks_overwrite(db):
    i = _film(db)
    a = db.log_watch(i, "2024-05-01", rating=8, source="letterboxd", source_key="k1")
    db.update_watch(a, rating=10)
    db.log_watch(i, "2024-05-01", rating=4, source="letterboxd", source_key="k1")
    assert db.get_watch_entry(a)["rating"] == 10
    db.delete_watch(a)
    db.log_watch(i, "2024-05-01", rating=4, source="letterboxd", source_key="k1")
    assert db.get_watch_log()[0] == 0


def test_update_watch_rejects_unknown_field(db):
    i = _film(db)
    a = db.log_watch(i, "2024-05-01")
    with pytest.raises(ValueError):
        db.update_watch(a, source="x")


def test_watch_log_filters_and_summary(db):
    a, b = _film(db, "A", runtime=60), _film(db, "B", runtime=120)
    db.log_watch(a, "2024-05-01", rating=10)
    db.log_watch(b, "2024-06-02", rating=6)
    total, entries, summary = db.get_watch_log(year=2024, month=5)
    assert total == 1 and entries[0]["item"]["title"] == "A"
    total, _, summary = db.get_watch_log(min_rating=9)
    assert total == 1
    _, _, s = db.get_watch_log()
    assert s["count"] == 2 and s["avg_rating"] == 8.0 and s["total_minutes"] == 180
    assert s["by_month"][0]["month"] == "2024-06"


def test_get_watchlist_filters_and_unknown_runtime(db):
    a = _film(db, "Short", 1990, runtime=80, director="Dir One")
    b = _film(db, "Long", 2001, runtime=150)
    c = db.upsert_item("film", "Unknown", 2005)
    for i in (a, b, c):
        db.set_watchlist(i, True)
    total, rows = db.get_watchlist(runtime_max=90)
    assert [r["title"] for r in rows] == ["Short"]
    assert db.get_watchlist()[0] == 3
    assert [r["title"] for r in db.get_watchlist(q="dir one")[1]] == ["Short"]
    assert {r["title"] for r in db.get_watchlist(decade=2000)[1]} == {"Long", "Unknown"}
    assert db.get_watchlist(sort="runtime")[1][0]["title"] == "Short"


def test_item_card_and_lookup(db):
    i = _film(db, "La Dolce Vita", 1960, director="Federico Fellini")
    card = db.get_item_card(i)
    assert card["directors"][0]["name"] == "Federico Fellini"
    assert card["status"]["seen"] is False
    assert [c["item_id"] for c in db.find_items_by_title("dolce")] == [i]
    assert db.find_items_by_title("%") == []


def test_writes_do_not_touch_documents_or_chunks(db):
    i = _film(db)
    doc = db.upsert_document(i, "tmdb", "en", "some text")
    db.upsert_chunk(i, doc, "whole", 0, "some text")
    before = db.stats()
    db.set_watchlist(i, True)
    e = db.log_watch(i, "2024-01-01", rating=5, liked=True)
    db.update_watch(e, rating=6)
    db.delete_watch(e)
    after = db.stats()
    for t in ("documents", "chunks"):
        assert before[t] == after[t]


def test_dates_normalised_and_domain_errors(db):
    from kinolog.core.db import InvalidInputError, NotFoundError

    i = _film(db)
    e = db.log_watch(i, "20240102")
    assert db.get_watch_entry(e)["watched_on"] == "2024-01-02"
    db.update_watch(e, watched_on="2024-W02-1")
    assert db.get_watch_entry(e)["watched_on"] == "2024-01-08"
    with pytest.raises(InvalidInputError):
        db.log_watch(i, "2024-1-1x")
    with pytest.raises(NotFoundError):
        db.set_watchlist(999, True)


def test_batch_helpers_handle_more_ids_than_sqlite_variable_limit(db):
    ids = [db.upsert_item("film", f"F{n}", 2000, runtime_min=100) for n in range(1200)]
    assert len(db.get_item_cards(ids)) == 1200
    from kinolog.core.collections import completion_deltas
    from kinolog.core.docfacts import item_facts

    assert len(completion_deltas(db, ids)) == 1200
    assert len(item_facts(db, ids)) == 1200
