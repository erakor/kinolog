"""Schema migrations: fresh schema, upgrading pre-migration databases, idempotence."""

import re
import sqlite3
from pathlib import Path

import pytest

from kinolog.store import Database, migrations

FIXTURES = Path(__file__).parent / "fixtures"
V3 = FIXTURES / "schema_v3.sql"  # the schema before migrations existed (+ columns)
V4 = FIXTURES / "schema_v4.sql"  # the current schema
SEPARATOR = "\n-- ---\n"
_ORDER = ("CREATE TABLE", "CREATE VIRTUAL TABLE", "CREATE UNIQUE INDEX", "CREATE INDEX",
          "CREATE TRIGGER")


def fixture_statements(path: Path = V4) -> list[str]:
    return [s.strip() for s in path.read_text(encoding="utf-8").split(SEPARATOR) if s.strip()]


def schema_dump(conn) -> list[str]:
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name"
    )
    return [r[0] for r in rows]


def old_style_db(path) -> sqlite3.Connection:
    """A database as the pre-migration code left it: full schema, user_version 0."""
    conn = sqlite3.connect(str(path))
    stmts = []
    for sql in fixture_statements(V3):
        if re.match(r"CREATE TABLE '?\"?chunks_fts_", sql):
            continue  # shadow tables are created by the FTS5 virtual table itself
        stmts.append(sql)
    stmts.sort(key=lambda s: next(i for i, p in enumerate(_ORDER) if s.startswith(p)))
    for sql in stmts:
        conn.execute(sql)
    conn.commit()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    return conn


def test_fresh_schema_matches_baseline():
    db = Database(":memory:")
    assert schema_dump(db.conn) == fixture_statements()


def test_fresh_database_is_at_latest_version():
    db = Database(":memory:")
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == migrations.latest_version() == 4


def test_migration_numbers_are_contiguous():
    assert [m.number for m in migrations.discover()] == [1, 2, 3, 4]


def test_upgrade_of_database_created_by_old_code(tmp_path):
    path = tmp_path / "old.db"
    old = old_style_db(path)
    old.execute("INSERT INTO items (item_type, title, year) VALUES ('film', 'La Dolce Vita', 1960)")
    old.commit()
    old.close()

    db = Database(path)
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == 4
    row = db.conn.execute("SELECT title, year FROM items").fetchone()
    assert (row["title"], row["year"]) == ("La Dolce Vita", 1960)
    assert schema_dump(db.conn) == fixture_statements()


def test_opening_twice_is_a_noop(tmp_path):
    path = tmp_path / "twice.db"
    first = Database(path)
    first.conn.execute("INSERT INTO items (item_type, title) VALUES ('film', 'A')")
    first.conn.commit()
    before = schema_dump(first.conn)
    first.close()

    second = Database(path)
    assert schema_dump(second.conn) == before
    assert second.conn.execute("PRAGMA user_version").fetchone()[0] == 4
    assert second.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_apply_returns_version_and_skips_applied():
    conn = sqlite3.connect(":memory:")
    assert migrations.apply(conn) == 4
    assert migrations.apply(conn) == 4


def test_failed_python_migration_rolls_back(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:")
    migrations.apply(conn)
    mig = migrations.Migration(5, "m005_boom.py", "py")

    class Boom:
        @staticmethod
        def upgrade(c):
            c.execute("CREATE TABLE half_done (x)")
            raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "discover", lambda: [*migrations.discover(), mig])
    monkeypatch.setattr(migrations.importlib, "import_module", lambda name: Boom)
    with pytest.raises(RuntimeError):
        migrations.apply(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'half_done'").fetchall()


def test_upgrade_adds_columns_missing_from_an_early_database(tmp_path):
    """A database from before the additive columns existed gains them on open."""
    from importlib import resources

    path = tmp_path / "early.db"
    conn = sqlite3.connect(str(path))
    conn.executescript(
        resources.files("kinolog.store.migrations").joinpath("m001_tables.sql").read_text()
    )
    assert "runtime_min" not in {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    conn.commit()
    conn.close()

    db = Database(path)
    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(items)")}
    assert {"runtime_min", "is_tv"} <= cols
    assert "edited" in {r["name"] for r in db.conn.execute("PRAGMA table_info(watch_log)")}


def test_database_from_the_pre_migration_omdb_code_upgrades_in_place(tmp_path):
    """Main's OMDb code already created external_ratings and items.imdb_id at user_version 0."""
    path = tmp_path / "omdb.db"
    conn = sqlite3.connect(str(path))
    stmts = [s for s in fixture_statements(V4) if not re.match(r"CREATE TABLE '?\"?chunks_fts_", s)]
    stmts.sort(key=lambda s: next(i for i, p in enumerate(_ORDER) if s.startswith(p)))
    for sql in stmts:
        conn.execute(sql)
    conn.commit()
    conn.close()

    db = Database(path)
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == 4
    assert schema_dump(db.conn) == fixture_statements(V4)
