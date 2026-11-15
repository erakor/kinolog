"""Schema definition (temporary: replaced by numbered migrations in the next commit)."""

from __future__ import annotations

import sqlite3

_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    item_type TEXT NOT NULL CHECK (item_type IN ('film', 'book')),
    title TEXT NOT NULL,
    original_title TEXT,
    year INTEGER,
    tmdb_id INTEGER UNIQUE,
    wikidata_id TEXT UNIQUE,
    isbn TEXT,
    openlibrary_id TEXT,
    match_confidence REAL,
    match_status TEXT CHECK (match_status IN ('auto', 'manual', 'queued', 'rejected'))
);

CREATE TABLE IF NOT EXISTS user_status (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    seen INTEGER DEFAULT 0,
    seen_date TEXT,
    on_watchlist INTEGER DEFAULT 0,
    liked INTEGER DEFAULT 0,
    liked_date TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS watch_log (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    watched_on TEXT NOT NULL,
    rating INTEGER,
    liked INTEGER,
    rewatch INTEGER DEFAULT 0,
    source TEXT NOT NULL,
    source_key TEXT,
    deleted_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source, source_key)
);

CREATE TABLE IF NOT EXISTS raw_cache (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    fetched_at TEXT,
    content_hash TEXT,
    path TEXT,
    PRIMARY KEY (source, external_id)
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    tmdb_person_id INTEGER UNIQUE,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credits (
    item_id INTEGER NOT NULL REFERENCES items(id),
    person_id INTEGER NOT NULL REFERENCES people(id),
    role TEXT NOT NULL,
    department TEXT,
    PRIMARY KEY (item_id, person_id, role)
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source TEXT,
    lang TEXT,
    text TEXT,
    content_hash TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    strategy TEXT NOT NULL,
    ord INTEGER NOT NULL,
    section_name TEXT,
    lang TEXT,
    text TEXT NOT NULL,
    token_count INTEGER,
    start_ms INTEGER,
    end_ms INTEGER,
    content_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS match_review_queue (
    item_id INTEGER PRIMARY KEY REFERENCES items(id),
    candidates_json TEXT,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY,
    run_at TEXT NOT NULL,
    suite TEXT NOT NULL,
    config_json TEXT,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    stdev REAL
);
"""

_FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, section_name,
    content='chunks', content_rowid='id'
);
"""

_FTS_TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text, section_name)
    VALUES (new.id, new.text, new.section_name);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section_name)
    VALUES ('delete', old.id, old.text, old.section_name);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text, section_name)
    VALUES ('delete', old.id, old.text, old.section_name);
    INSERT INTO chunks_fts(rowid, text, section_name)
    VALUES (new.id, new.text, new.section_name);
END;
"""

_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type);
CREATE INDEX IF NOT EXISTS idx_items_tmdb ON items(tmdb_id);
CREATE INDEX IF NOT EXISTS idx_items_title_year ON items(title, year);
CREATE INDEX IF NOT EXISTS idx_user_status_seen ON user_status(seen);
CREATE INDEX IF NOT EXISTS idx_user_status_liked ON user_status(liked);
CREATE INDEX IF NOT EXISTS idx_documents_item ON documents(item_id);
CREATE INDEX IF NOT EXISTS idx_chunks_item ON chunks(item_id);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_strategy ON chunks(strategy);
CREATE INDEX IF NOT EXISTS idx_credits_item ON credits(item_id);
CREATE INDEX IF NOT EXISTS idx_credits_person ON credits(person_id);
CREATE INDEX IF NOT EXISTS idx_watch_log_item ON watch_log(item_id);
CREATE INDEX IF NOT EXISTS idx_watch_log_date ON watch_log(watched_on);
"""


# (table, column, declaration) added after the initial schema.
_ADDED_COLUMNS = [
    ("items", "runtime_min", "INTEGER"),
    ("items", "is_tv", "INTEGER DEFAULT 0"),
    ("user_status", "rating", "INTEGER"),
    ("user_status", "watchlist_added_at", "TEXT"),
    ("user_status", "watchlist_removed_at", "TEXT"),
    ("user_status", "manual_updated_at", "TEXT"),
    ("watch_log", "edited", "INTEGER DEFAULT 0"),
]


def ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> bool:
    """Add a column if missing. Returns True if added."""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column in cols:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    conn.commit()
    return True


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables, indexes, triggers, and FTS."""
    cur = conn.cursor()
    cur.executescript(_TABLES_SQL)
    for table, column, decl in _ADDED_COLUMNS:
        ensure_column(conn, table, column, decl)
    cur.executescript(_FTS_SQL)
    cur.executescript(_FTS_TRIGGERS_SQL)
    cur.executescript(_INDEXES_SQL)
    conn.commit()
