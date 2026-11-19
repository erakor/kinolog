"""Tests for the database layer."""

import pytest

from kinolog.store import Database, content_hash


@pytest.fixture
def db():
    """In-memory test database."""
    d = Database(":memory:")
    yield d
    d.close()


class TestSchema:
    def test_tables_created(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in tables}
        assert "items" in names
        assert "user_status" in names
        assert "documents" in names
        assert "chunks" in names
        assert "people" in names
        assert "credits" in names
        assert "eval_runs" in names
        assert "raw_cache" in names
        assert "match_review_queue" in names

    def test_fts_created(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
        ).fetchall()
        assert len(tables) == 1

    def test_foreign_keys_enabled(self, db):
        row = db.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1

    def test_wal_mode(self, db):
        # In-memory DBs may not support WAL, but the pragma shouldn't error
        row = db.execute("PRAGMA journal_mode").fetchone()
        assert row[0] in ("wal", "memory")


class TestItems:
    def test_upsert_item_insert(self, db):
        item_id = db.upsert_item("film", "La Dolce Vita", 1960)
        assert item_id > 0

        item = db.get_item(item_id)
        assert item["title"] == "La Dolce Vita"
        assert item["year"] == 1960
        assert item["item_type"] == "film"

    def test_upsert_item_update(self, db):
        id1 = db.upsert_item("film", "La Dolce Vita", 1960)
        id2 = db.upsert_item("film", "La Dolce Vita", 1960, tmdb_id=539)
        assert id1 == id2

        item = db.get_item(id1)
        assert item["tmdb_id"] == 539

    def test_upsert_item_different_year(self, db):
        id1 = db.upsert_item("film", "Solaris", 1972)
        id2 = db.upsert_item("film", "Solaris", 2002)
        assert id1 != id2

    def test_get_items_by_type(self, db):
        db.upsert_item("film", "Film 1", 2000)
        db.upsert_item("book", "Book 1", 2000)
        db.upsert_item("film", "Film 2", 2001)

        films = db.get_items(item_type="film")
        assert len(films) == 2

        books = db.get_items(item_type="book")
        assert len(books) == 1


class TestUserStatus:
    def test_upsert_user_status(self, db):
        item_id = db.upsert_item("film", "Test Film", 2000)
        db.upsert_user_status(item_id, seen=1, seen_date="2024-01-01")

        row = db.execute("SELECT * FROM user_status WHERE item_id = ?", (item_id,)).fetchone()
        assert row["seen"] == 1
        assert row["seen_date"] == "2024-01-01"

    def test_update_existing_status(self, db):
        item_id = db.upsert_item("film", "Test Film", 2000)
        db.upsert_user_status(item_id, seen=1)
        db.upsert_user_status(item_id, liked=1, liked_date="2024-06-01")

        row = db.execute("SELECT * FROM user_status WHERE item_id = ?", (item_id,)).fetchone()
        assert row["seen"] == 1
        assert row["liked"] == 1

    def test_get_items_with_status_filter(self, db):
        id1 = db.upsert_item("film", "Film 1", 2000)
        id2 = db.upsert_item("film", "Film 2", 2001)
        db.upsert_user_status(id1, seen=1, liked=1)
        db.upsert_user_status(id2, seen=1, liked=0)

        liked = db.get_items(liked=True)
        assert len(liked) == 1
        assert liked[0]["title"] == "Film 1"


class TestDocumentsAndChunks:
    def test_upsert_document(self, db):
        item_id = db.upsert_item("film", "Test", 2000)
        doc_id = db.upsert_document(item_id, "tmdb", "en", "Some text about the film")
        assert doc_id > 0

    def test_document_idempotent(self, db):
        item_id = db.upsert_item("film", "Test", 2000)
        id1 = db.upsert_document(item_id, "tmdb", "en", "Same text")
        id2 = db.upsert_document(item_id, "tmdb", "en", "Same text")
        assert id1 == id2

    def test_document_update_on_change(self, db):
        item_id = db.upsert_item("film", "Test", 2000)
        id1 = db.upsert_document(item_id, "tmdb", "en", "Version 1")
        id2 = db.upsert_document(item_id, "tmdb", "en", "Version 2")
        assert id1 == id2

        doc = db.execute("SELECT text FROM documents WHERE id = ?", (id1,)).fetchone()
        assert doc["text"] == "Version 2"

    def test_chunk_fts_sync(self, db):
        item_id = db.upsert_item("film", "Test", 2000)
        doc_id = db.upsert_document(item_id, "tmdb", "en", "Test doc")
        chunk_id = db.upsert_chunk(
            item_id,
            doc_id,
            "whole",
            0,
            "A beautiful film about love in Paris",
        )

        # FTS should find it
        rows = db.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'Paris'").fetchall()
        assert len(rows) == 1
        assert rows[0]["rowid"] == chunk_id


class TestPeopleAndCredits:
    def test_upsert_person(self, db):
        pid = db.upsert_person("Federico Fellini", tmdb_person_id=4415)
        assert pid > 0

        # Same TMDB ID returns same person
        pid2 = db.upsert_person("Fellini", tmdb_person_id=4415)
        assert pid == pid2

    def test_upsert_credit(self, db):
        item_id = db.upsert_item("film", "8½", 1963)
        pid = db.upsert_person("Federico Fellini", tmdb_person_id=4415)
        db.upsert_credit(item_id, pid, "Director", "Directing")

        rows = db.execute(
            "SELECT * FROM credits WHERE item_id = ? AND person_id = ?",
            (item_id, pid),
        ).fetchall()
        assert len(rows) == 1


class TestReviewQueue:
    def test_queue_and_resolve(self, db):
        item_id = db.upsert_item("film", "Ambiguous Film", 2000)
        db.queue_for_review(item_id, [{"tmdb_id": 123, "title": "Film A"}], "ambiguous")

        queue = db.get_review_queue()
        assert len(queue) == 1
        assert queue[0]["title"] == "Ambiguous Film"

        db.resolve_review(item_id, tmdb_id=123)
        queue = db.get_review_queue()
        assert len(queue) == 0

        item = db.get_item(item_id)
        assert item["tmdb_id"] == 123
        assert item["match_status"] == "manual"


class TestEvalRuns:
    def test_log_eval(self, db):
        db.log_eval("test_suite", "mrr", 0.75, stdev=0.05, config={"k": 5})

        rows = db.execute("SELECT * FROM eval_runs").fetchall()
        assert len(rows) == 1
        assert rows[0]["value"] == 0.75
        assert rows[0]["suite"] == "test_suite"


class TestContentHash:
    def test_deterministic(self):
        assert content_hash("hello") == content_hash("hello")

    def test_different_texts(self):
        assert content_hash("hello") != content_hash("world")


def test_ensure_column_idempotent_on_reopened_file(tmp_path):
    path = tmp_path / "x.db"
    d = Database(path)
    assert d._ensure_column("items", "extra_col", "INTEGER") is True
    assert d._ensure_column("items", "extra_col", "INTEGER") is False
    d.close()
    d2 = Database(path)
    assert d2._ensure_column("items", "extra_col", "INTEGER") is False
    d2.close()


def test_check_same_thread_false_allows_cross_thread_use():
    import threading

    d = Database(":memory:", check_same_thread=False)
    out = []

    def work():
        out.append(d.upsert_item("film", "Thread", 2000))

    t = threading.Thread(target=work)
    t.start()
    t.join()
    assert len(out) == 1
    d.close()


def test_new_columns_and_watch_log_exist():
    d = Database(":memory:")
    item = d.upsert_item("film", "Short", 2000, runtime_min=12, is_tv=0)
    assert d.get_item(item)["runtime_min"] == 12
    d.upsert_user_status(item, rating=8, watchlist_added_at="2024-01-01")
    row = d.execute("SELECT rating, watchlist_added_at FROM user_status").fetchone()
    assert row["rating"] == 8 and row["watchlist_added_at"] == "2024-01-01"
    d.execute(
        "INSERT INTO watch_log (item_id, watched_on, source, created_at, updated_at)"
        " VALUES (?, '2024-01-01', 'manual', 'x', 'x')",
        (item,),
    )
    assert d.stats()["watch_log"] == 1


def test_old_db_gains_columns(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    c = sqlite3.connect(path)
    c.executescript(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, item_type TEXT NOT NULL, title TEXT NOT NULL,"
        " original_title TEXT, year INTEGER, tmdb_id INTEGER UNIQUE, wikidata_id TEXT UNIQUE,"
        " isbn TEXT, openlibrary_id TEXT, match_confidence REAL, match_status TEXT);"
        "CREATE TABLE user_status (item_id INTEGER PRIMARY KEY, seen INTEGER DEFAULT 0,"
        " seen_date TEXT, on_watchlist INTEGER DEFAULT 0, liked INTEGER DEFAULT 0,"
        " liked_date TEXT, source TEXT);"
    )
    c.commit()
    c.close()
    d = Database(path)
    cols = {r["name"] for r in d.execute("PRAGMA table_info(items)")}
    assert {"runtime_min", "is_tv"} <= cols
    d.close()
