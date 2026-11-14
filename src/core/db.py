"""Database layer: SQLite with FTS5, optional sqlite-vec, and schema management."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

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
"""


def content_hash(text: str) -> str:
    """SHA-256 hex digest of text, used for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Database:
    """SQLite database with FTS5 and optional sqlite-vec support."""

    def __init__(self, db_path: str | Path = "data/index.db"):
        if str(db_path) != ":memory:":
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")

        self._vec_available = self._try_load_vec()
        self._init_schema()

    def _try_load_vec(self) -> bool:
        """Try to load the sqlite-vec extension."""
        try:
            import sqlite_vec

            sqlite_vec.load(self.conn)
            logger.info("sqlite-vec loaded successfully")
            return True
        except (ImportError, Exception) as e:
            logger.warning("sqlite-vec not available: %s", e)
            return False

    @property
    def vec_available(self) -> bool:
        return self._vec_available

    def _init_schema(self):
        """Create all tables, indexes, triggers, and FTS."""
        cur = self.conn.cursor()
        cur.executescript(_TABLES_SQL)
        cur.executescript(_FTS_SQL)
        cur.executescript(_FTS_TRIGGERS_SQL)
        cur.executescript(_INDEXES_SQL)
        self.conn.commit()

    # --- Vector tables ---

    def try_create_vec_table(self, model_name: str, dim: int) -> bool:
        """Create a vec0 table for a given model. Returns True if created, False if vec not available."""
        if not self._vec_available:
            logger.warning("Cannot create vec table: sqlite-vec not loaded")
            return False
        table_name = f"vec_{model_name}"
        sql = f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[{dim}])"
        self.conn.execute(sql)
        self.conn.commit()
        logger.info("Created vector table %s (dim=%d)", table_name, dim)
        return True

    # --- Item CRUD ---

    def upsert_item(
        self,
        item_type: str,
        title: str,
        year: int | None = None,
        **kwargs: Any,
    ) -> int:
        """Insert or update an item by (title, year, item_type). Returns the item id."""
        # Check if exists
        row = self.conn.execute(
            "SELECT id FROM items WHERE title = ? AND year IS ? AND item_type = ?",
            (title, year, item_type),
        ).fetchone()

        allowed = {
            "original_title", "tmdb_id", "wikidata_id", "isbn",
            "openlibrary_id", "match_confidence", "match_status",
        }
        filtered = {k: v for k, v in kwargs.items() if k in allowed and v is not None}

        if row:
            item_id = row["id"]
            if filtered:
                set_clause = ", ".join(f"{k} = ?" for k in filtered)
                vals = list(filtered.values()) + [item_id]
                self.conn.execute(f"UPDATE items SET {set_clause} WHERE id = ?", vals)
                self.conn.commit()
            return item_id

        cols = ["item_type", "title", "year"] + list(filtered.keys())
        placeholders = ", ".join("?" for _ in cols)
        vals = [item_type, title, year] + list(filtered.values())
        cur = self.conn.execute(
            f"INSERT INTO items ({', '.join(cols)}) VALUES ({placeholders})", vals
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def upsert_user_status(self, item_id: int, **kwargs: Any):
        """Insert or update user_status for an item."""
        allowed = {"seen", "seen_date", "on_watchlist", "liked", "liked_date", "source"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}

        row = self.conn.execute(
            "SELECT item_id FROM user_status WHERE item_id = ?", (item_id,)
        ).fetchone()

        if row:
            if filtered:
                set_clause = ", ".join(f"{k} = ?" for k in filtered)
                vals = list(filtered.values()) + [item_id]
                self.conn.execute(f"UPDATE user_status SET {set_clause} WHERE item_id = ?", vals)
        else:
            filtered["item_id"] = item_id
            cols = list(filtered.keys())
            placeholders = ", ".join("?" for _ in cols)
            vals = list(filtered.values())
            self.conn.execute(
                f"INSERT INTO user_status ({', '.join(cols)}) VALUES ({placeholders})", vals
            )
        self.conn.commit()

    def get_item(self, item_id: int) -> dict | None:
        """Get a single item by id."""
        row = self.conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return dict(row) if row else None

    def get_items(
        self,
        item_type: str | None = None,
        seen: bool | None = None,
        liked: bool | None = None,
        on_watchlist: bool | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Get items with optional filters."""
        sql = "SELECT i.* FROM items i"
        conditions = []
        params: list[Any] = []

        needs_status = any(x is not None for x in [seen, liked, on_watchlist])
        if needs_status:
            sql += " LEFT JOIN user_status us ON i.id = us.item_id"

        if item_type:
            conditions.append("i.item_type = ?")
            params.append(item_type)
        if seen is not None:
            conditions.append("us.seen = ?")
            params.append(1 if seen else 0)
        if liked is not None:
            conditions.append("us.liked = ?")
            params.append(1 if liked else 0)
        if on_watchlist is not None:
            conditions.append("us.on_watchlist = ?")
            params.append(1 if on_watchlist else 0)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        if limit:
            sql += " LIMIT ?"
            params.append(limit)

        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # --- Documents & Chunks ---

    def upsert_document(
        self,
        item_id: int,
        source: str,
        lang: str,
        text: str,
    ) -> int:
        """Insert or update a document. Returns document id."""
        c_hash = content_hash(text)
        row = self.conn.execute(
            "SELECT id, content_hash FROM documents WHERE item_id = ? AND source = ? AND lang = ?",
            (item_id, source, lang),
        ).fetchone()

        if row:
            if row["content_hash"] == c_hash:
                return row["id"]  # unchanged
            self.conn.execute(
                "UPDATE documents SET text = ?, content_hash = ? WHERE id = ?",
                (text, c_hash, row["id"]),
            )
            self.conn.commit()
            return row["id"]

        cur = self.conn.execute(
            "INSERT INTO documents (item_id, source, lang, text, content_hash) VALUES (?, ?, ?, ?, ?)",
            (item_id, source, lang, text, c_hash),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def upsert_chunk(
        self,
        item_id: int,
        document_id: int,
        strategy: str,
        ord: int,
        text: str,
        section_name: str | None = None,
        lang: str | None = None,
        token_count: int | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> int:
        """Insert or update a chunk. Returns chunk id."""
        c_hash = content_hash(text)
        row = self.conn.execute(
            "SELECT id, content_hash FROM chunks WHERE document_id = ? AND strategy = ? AND ord = ?",
            (document_id, strategy, ord),
        ).fetchone()

        if row:
            if row["content_hash"] == c_hash:
                return row["id"]
            self.conn.execute(
                """UPDATE chunks SET item_id=?, text=?, section_name=?, lang=?,
                   token_count=?, start_ms=?, end_ms=?, content_hash=? WHERE id=?""",
                (item_id, text, section_name, lang, token_count, start_ms, end_ms, c_hash, row["id"]),
            )
            self.conn.commit()
            return row["id"]

        cur = self.conn.execute(
            """INSERT INTO chunks (item_id, document_id, strategy, ord, section_name,
               lang, text, token_count, start_ms, end_ms, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_id, document_id, strategy, ord, section_name, lang, text,
             token_count, start_ms, end_ms, c_hash),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def delete_chunks_for_document(self, document_id: int, strategy: str | None = None):
        """Delete chunks for a document, optionally filtered by strategy."""
        if strategy:
            self.conn.execute(
                "DELETE FROM chunks WHERE document_id = ? AND strategy = ?",
                (document_id, strategy),
            )
        else:
            self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        self.conn.commit()

    # --- People & Credits ---

    def upsert_person(self, name: str, tmdb_person_id: int | None = None) -> int:
        """Insert or update a person. Returns person id."""
        if tmdb_person_id:
            row = self.conn.execute(
                "SELECT id FROM people WHERE tmdb_person_id = ?", (tmdb_person_id,)
            ).fetchone()
            if row:
                return row["id"]

        row = self.conn.execute(
            "SELECT id FROM people WHERE name = ? AND tmdb_person_id IS ?",
            (name, tmdb_person_id),
        ).fetchone()
        if row:
            return row["id"]

        cur = self.conn.execute(
            "INSERT INTO people (name, tmdb_person_id) VALUES (?, ?)",
            (name, tmdb_person_id),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def upsert_credit(self, item_id: int, person_id: int, role: str, department: str | None = None):
        """Insert or ignore a credit."""
        self.conn.execute(
            """INSERT OR IGNORE INTO credits (item_id, person_id, role, department)
               VALUES (?, ?, ?, ?)""",
            (item_id, person_id, role, department),
        )
        self.conn.commit()

    # --- Raw Cache ---

    def cache_get(self, source: str, external_id: str) -> dict | None:
        """Check if we have a cached entry."""
        row = self.conn.execute(
            "SELECT * FROM raw_cache WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()
        return dict(row) if row else None

    def cache_put(self, source: str, external_id: str, path: str, content_hash: str | None = None):
        """Insert or update a cache entry."""
        from datetime import datetime, timezone

        self.conn.execute(
            """INSERT OR REPLACE INTO raw_cache (source, external_id, fetched_at, content_hash, path)
               VALUES (?, ?, ?, ?, ?)""",
            (source, external_id, datetime.now(timezone.utc).isoformat(), content_hash, path),
        )
        self.conn.commit()

    # --- Match Review Queue ---

    def queue_for_review(self, item_id: int, candidates: list[dict], reason: str):
        """Add an item to the match review queue."""
        self.conn.execute(
            "INSERT OR REPLACE INTO match_review_queue (item_id, candidates_json, reason) VALUES (?, ?, ?)",
            (item_id, json.dumps(candidates, ensure_ascii=False), reason),
        )
        self.conn.commit()

    def get_review_queue(self) -> list[dict]:
        """Get all items in the review queue."""
        rows = self.conn.execute(
            """SELECT q.*, i.title, i.year, i.item_type
               FROM match_review_queue q JOIN items i ON q.item_id = i.id"""
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["candidates"] = json.loads(d.pop("candidates_json"))
            result.append(d)
        return result

    def resolve_review(self, item_id: int, tmdb_id: int | None = None, reject: bool = False):
        """Resolve a review queue entry."""
        if reject:
            self.conn.execute(
                "UPDATE items SET match_status = 'rejected' WHERE id = ?", (item_id,)
            )
        elif tmdb_id is not None:
            self.conn.execute(
                "UPDATE items SET tmdb_id = ?, match_status = 'manual', match_confidence = 1.0 WHERE id = ?",
                (tmdb_id, item_id),
            )
        self.conn.execute("DELETE FROM match_review_queue WHERE item_id = ?", (item_id,))
        self.conn.commit()

    # --- Eval Runs ---

    def log_eval(
        self,
        suite: str,
        metric: str,
        value: float,
        stdev: float | None = None,
        config: dict | None = None,
    ):
        """Log an evaluation run."""
        from datetime import datetime, timezone

        self.conn.execute(
            "INSERT INTO eval_runs (run_at, suite, config_json, metric, value, stdev) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                suite,
                json.dumps(config) if config else None,
                metric,
                value,
                stdev,
            ),
        )
        self.conn.commit()

    # --- Low-level ---

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list[tuple]):
        self.conn.executemany(sql, params_list)
        self.conn.commit()

    def __enter__(self):
        self.conn.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        return False

    def close(self):
        self.conn.close()

    def stats(self) -> dict[str, int]:
        """Quick table row counts."""
        tables = ["items", "user_status", "documents", "chunks", "people", "credits", "eval_runs"]
        result = {}
        for t in tables:
            row = self.conn.execute(f"SELECT COUNT(*) as c FROM {t}").fetchone()
            result[t] = row["c"]
        return result
