"""Tests for the Letterboxd loader."""

import csv

import pytest

from kinolog.sources.letterboxd.load import compute_first_heart_date, load_letterboxd
from kinolog.store import Database


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def export_dir(tmp_path):
    """Create a fake Letterboxd export directory."""
    # watched.csv
    watched = tmp_path / "watched.csv"
    with open(watched, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Name", "Year", "Letterboxd URI"])
        writer.writeheader()
        writer.writerow({"Date": "2024-01-15", "Name": "La Dolce Vita", "Year": "1960",
                         "Letterboxd URI": "https://letterboxd.com/film/la-dolce-vita/"})
        writer.writerow({"Date": "2024-02-01", "Name": "8½", "Year": "1963",
                         "Letterboxd URI": "https://letterboxd.com/film/8-half/"})
        writer.writerow({"Date": "2024-03-10", "Name": "Le Mépris", "Year": "1963",
                         "Letterboxd URI": "https://letterboxd.com/film/contempt/"})

    # watchlist.csv
    watchlist = tmp_path / "watchlist.csv"
    with open(watchlist, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Name", "Year", "Letterboxd URI"])
        writer.writeheader()
        writer.writerow({"Date": "2024-04-01", "Name": "Solaris", "Year": "1972",
                         "Letterboxd URI": "https://letterboxd.com/film/solaris/"})

    # likes/films.csv
    likes_dir = tmp_path / "likes"
    likes_dir.mkdir()
    likes = likes_dir / "films.csv"
    with open(likes, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Name", "Year", "Letterboxd URI"])
        writer.writeheader()
        writer.writerow({"Date": "2024-06-01", "Name": "La Dolce Vita", "Year": "1960",
                         "Letterboxd URI": "https://letterboxd.com/film/la-dolce-vita/"})
        writer.writerow({"Date": "2024-06-15", "Name": "8½", "Year": "1963",
                         "Letterboxd URI": "https://letterboxd.com/film/8-half/"})

    return tmp_path


def test_load_letterboxd(db, export_dir):
    stats = load_letterboxd(db, export_dir)

    assert stats["watched"] == 3
    assert stats["watchlist"] == 1
    assert stats["likes"] == 2
    assert stats["first_heart_date"] == "2024-06-01"

    # Check items
    items = db.get_items(item_type="film")
    assert len(items) == 4  # 3 watched + 1 watchlist (no overlap here)

    # Check user status
    liked_items = db.get_items(liked=True)
    assert len(liked_items) == 2


def test_first_heart_date():
    rows = [
        {"Date": "2024-06-01"},
        {"Date": "2024-05-15"},
        {"Date": "2024-07-01"},
    ]
    assert compute_first_heart_date(rows) == "2024-05-15"


def test_idempotent_load(db, export_dir):
    stats1 = load_letterboxd(db, export_dir)
    stats2 = load_letterboxd(db, export_dir)

    # Should not duplicate items
    items = db.get_items(item_type="film")
    assert len(items) == 4


def _write(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


@pytest.fixture
def diary_dir(tmp_path):
    _write(tmp_path / "watched.csv", ["Date", "Name", "Year", "Letterboxd URI"], [
        {"Date": "2024-01-20", "Name": "Solaris", "Year": "1972", "Letterboxd URI": "u/solaris"},
    ])
    _write(tmp_path / "diary.csv",
           ["Date", "Name", "Year", "Letterboxd URI", "Rating", "Rewatch", "Tags", "Watched Date"], [
        {"Date": "2024-01-21", "Name": "Solaris", "Year": "1972", "Letterboxd URI": "u/solaris",
         "Rating": "4.5", "Rewatch": "", "Tags": "", "Watched Date": "2024-01-20"},
        {"Date": "2024-03-01", "Name": "Solaris", "Year": "1972", "Letterboxd URI": "u/solaris",
         "Rating": "5", "Rewatch": "Yes", "Tags": "", "Watched Date": "2024-02-28"},
    ])
    _write(tmp_path / "ratings.csv", ["Date", "Name", "Year", "Letterboxd URI", "Rating"], [
        {"Date": "2024-03-01", "Name": "Solaris", "Year": "1972", "Letterboxd URI": "u/solaris",
         "Rating": "5"},
    ])
    _write(tmp_path / "watchlist.csv", ["Date", "Name", "Year", "Letterboxd URI"], [
        {"Date": "2023-02-11", "Name": "Stalker", "Year": "1979", "Letterboxd URI": "u/stalker"},
    ])
    return tmp_path


def test_diary_rating_rewatch_and_added_date(db, diary_dir):
    stats = load_letterboxd(db, diary_dir)
    assert stats["diary"] == 2 and stats["ratings"] == 1
    total, entries, _ = db.get_watch_log()
    assert total == 2
    by_date = {e["watched_on"]: e for e in entries}
    assert by_date["2024-01-20"]["rating"] == 9 and not by_date["2024-01-20"]["rewatch"]
    assert by_date["2024-02-28"]["rating"] == 10 and by_date["2024-02-28"]["rewatch"]
    card = entries[0]["item"]
    assert card["status"]["rating"] == 10
    # seen_date is the latest viewing, not the last row processed
    row = db.execute("SELECT seen_date FROM user_status WHERE item_id = ?", (card["item_id"],)).fetchone()
    assert row["seen_date"] == "2024-02-28"
    stalker = db.find_items_by_title("Stalker")[0]
    assert stalker["added_at"] == "2023-02-11"


def test_reimport_is_idempotent_for_log(db, diary_dir):
    load_letterboxd(db, diary_dir)
    load_letterboxd(db, diary_dir)
    assert db.get_watch_log()[0] == 2


def test_reimport_does_not_resurrect_deleted_entry(db, diary_dir):
    load_letterboxd(db, diary_dir)
    _, entries, _ = db.get_watch_log()
    for e in entries:
        db.delete_watch(e["entry_id"])
    stats = load_letterboxd(db, diary_dir)
    assert db.get_watch_log()[0] == 0
    sol = db.find_items_by_title("Solaris")[0]
    assert sol["status"]["seen"] is False  # watched.csv row skipped too
    assert stats["skipped_manual_override"] >= 1


def test_reimport_keeps_manual_dequeue(db, diary_dir):
    load_letterboxd(db, diary_dir)
    stalker = db.find_items_by_title("Stalker")[0]["item_id"]
    db.set_watchlist(stalker, False)
    stats = load_letterboxd(db, diary_dir)
    assert db.get_watchlist_ids() == []
    assert stats["skipped_manual_override"] >= 1


def test_newer_letterboxd_add_requeues(db, diary_dir):
    load_letterboxd(db, diary_dir)
    stalker = db.find_items_by_title("Stalker")[0]["item_id"]
    db.set_watchlist(stalker, False, at="2023-06-01T00:00:00+00:00")
    _write(diary_dir / "watchlist.csv", ["Date", "Name", "Year", "Letterboxd URI"], [
        {"Date": "2024-09-01", "Name": "Stalker", "Year": "1979", "Letterboxd URI": "u/stalker"},
    ])
    load_letterboxd(db, diary_dir)
    assert db.get_watchlist_ids() == [stalker]


def test_manual_rating_and_like_survive_reimport(db, diary_dir):
    _write(diary_dir / "likes" / "films.csv", ["Date", "Name", "Year", "Letterboxd URI"], [
        {"Date": "2000-01-01", "Name": "Solaris", "Year": "1972", "Letterboxd URI": "u/solaris"},
    ])
    load_letterboxd(db, diary_dir)
    sol = db.find_items_by_title("Solaris")[0]["item_id"]
    # manual edits dated after the export rows (manual_updated_at is "now")
    db.set_rating(sol, 3)
    db.set_liked(sol, False)
    load_letterboxd(db, diary_dir)
    card = db.get_item_card(sol)
    assert card["status"]["rating"] == 3 and card["status"]["liked"] is False


def test_edited_entry_survives_reimport(db, diary_dir):
    load_letterboxd(db, diary_dir)
    _, entries, _ = db.get_watch_log()
    target = next(e for e in entries if e["watched_on"] == "2024-01-20")
    db.update_watch(target["entry_id"], rating=2)
    load_letterboxd(db, diary_dir)
    assert db.get_watch_entry(target["entry_id"])["rating"] == 2


def test_zip_with_traversal_rejected(db, tmp_path):
    import zipfile

    z = tmp_path / "letterboxd-evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../evil.csv", "x")
    with pytest.raises(ValueError):
        load_letterboxd(db, tmp_path)
