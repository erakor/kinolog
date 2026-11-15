"""tmdb_movies / person_filmography tables and their store writers."""

import json

from kinolog.store import Database, migrations


def _count(db, table):
    return db.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def test_tables_exist_and_stats_count_them():
    db = Database(":memory:")
    s = db.stats()
    assert s["tmdb_movies"] == 0 and s["person_filmography"] == 0


def test_upsert_tmdb_movie_is_idempotent_and_normalizes():
    db = Database(":memory:")
    db.upsert_tmdb_movie(1, "A", runtime=0, release_date="", genre_ids=[99], year=2000)
    db.upsert_tmdb_movie(1, "A2", runtime=95, status="Released", is_video=True)
    assert _count(db, "tmdb_movies") == 1
    row = db.execute("SELECT * FROM tmdb_movies WHERE tmdb_id = 1").fetchone()
    assert (row["title"], row["runtime"], row["is_video"]) == ("A2", 95, 1)
    db.upsert_tmdb_movie(2, "B", runtime=0, release_date="")
    row = db.execute("SELECT * FROM tmdb_movies WHERE tmdb_id = 2").fetchone()
    assert row["runtime"] is None and row["release_date"] is None
    assert json.loads(row["genre_ids"]) == []


def test_set_person_filmography_is_idempotent_and_additive():
    db = Database(":memory:")
    p = db.upsert_person("Ann", tmdb_person_id=1)
    db.set_person_filmography(p, [10, 11, 10])
    db.set_person_filmography(p, [11, 12])
    ids = {r["tmdb_id"] for r in db.execute("SELECT tmdb_id FROM person_filmography")}
    assert ids == {10, 11, 12}


def test_reopening_a_file_database_keeps_rows(tmp_path):
    path = str(tmp_path / "k.db")
    db = Database(path)
    db.upsert_tmdb_movie(1, "A")
    db.close()
    again = Database(path)
    assert _count(again, "tmdb_movies") == 1
    assert again.conn.execute("PRAGMA user_version").fetchone()[0] == migrations.latest_version()
