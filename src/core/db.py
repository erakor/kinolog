"""Database layer: SQLite with FTS5, optional sqlite-vec, and schema management."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import date, datetime, timezone
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid date (expected YYYY-MM-DD): {value!r}") from e
    return value


def _check_rating(rating: int | None) -> int | None:
    if rating is None:
        return None
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 10:
        raise ValueError(f"Rating must be an integer 1..10 (half-stars), got {rating!r}")
    return rating


def _title_or_director(q: str) -> tuple[str, list[str]]:
    """SQL fragment (alias i) matching a title or a director name, plus its params."""
    like = f"%{q.strip()}%"
    return (
        """ AND (i.title LIKE ? OR EXISTS (SELECT 1 FROM credits c
               JOIN people p ON p.id = c.person_id
               WHERE c.item_id = i.id AND c.role = 'Director' AND p.name LIKE ?))""",
        [like, like],
    )


def content_hash(text: str) -> str:
    """SHA-256 hex digest of text, used for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Database:
    """SQLite database with FTS5 and optional sqlite-vec support."""

    def __init__(self, db_path: str | Path = "data/index.db", check_same_thread: bool = True):
        if str(db_path) != ":memory:":
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path), check_same_thread=check_same_thread)
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
        self._apply_additive_columns()
        cur.executescript(_FTS_SQL)
        cur.executescript(_FTS_TRIGGERS_SQL)
        cur.executescript(_INDEXES_SQL)
        self.conn.commit()

    def _apply_additive_columns(self):
        """Columns added after the first schema version (safe on existing DBs)."""
        for table, column, decl in _ADDED_COLUMNS:
            self._ensure_column(table, column, decl)

    def _ensure_column(self, table: str, column: str, decl: str) -> bool:
        """Add a column if missing (no migrations framework). Returns True if added."""
        cols = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
        if column in cols:
            return False
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        self.conn.commit()
        return True

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
            "runtime_min", "is_tv",
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
        allowed = {
            "seen", "seen_date", "on_watchlist", "liked", "liked_date", "source",
            "rating", "watchlist_added_at", "watchlist_removed_at", "manual_updated_at",
        }
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

    # --- User actions (UI mutations) ---

    def _ensure_status(self, item_id: int):
        if not self.conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone():
            raise KeyError(f"No such item: {item_id}")
        self.conn.execute("INSERT OR IGNORE INTO user_status (item_id) VALUES (?)", (item_id,))

    def set_watchlist(
        self, item_id: int, on: bool, *, at: str | None = None, manual: bool = True
    ) -> None:
        """Add/remove an item from the watchlist. Removal is recorded, never a row delete."""
        self._ensure_status(item_id)
        stamp = at or _now()
        if on:
            self.conn.execute(
                """UPDATE user_status SET on_watchlist = 1, watchlist_added_at = ?,
                   watchlist_removed_at = NULL WHERE item_id = ?""",
                (stamp, item_id),
            )
        else:
            self.conn.execute(
                "UPDATE user_status SET on_watchlist = 0, watchlist_removed_at = ? WHERE item_id = ?",
                (stamp, item_id),
            )
        if manual:
            self.conn.execute(
                "UPDATE user_status SET manual_updated_at = ? WHERE item_id = ?", (_now(), item_id)
            )
        self.conn.commit()

    def log_watch(
        self,
        item_id: int,
        watched_on: str,
        *,
        rating: int | None = None,
        liked: bool | None = None,
        rewatch: bool = False,
        source: str = "manual",
        source_key: str | None = None,
    ) -> int:
        """Record a viewing. Idempotent by (source, source_key); tombstones are respected."""
        _check_date(watched_on)
        _check_rating(rating)
        self._ensure_status(item_id)
        now = _now()
        liked_v = None if liked is None else int(bool(liked))

        existing = None
        if source_key is not None:
            existing = self.conn.execute(
                "SELECT id, deleted_at, edited FROM watch_log WHERE source = ? AND source_key = ?",
                (source, source_key),
            ).fetchone()
        if existing:
            if not existing["deleted_at"] and not existing["edited"]:
                self.conn.execute(
                    """UPDATE watch_log SET watched_on = ?, rating = ?, liked = ?, rewatch = ?,
                       updated_at = ? WHERE id = ?""",
                    (watched_on, rating, liked_v, int(rewatch), now, existing["id"]),
                )
                self.conn.commit()
            return existing["id"]

        cur = self.conn.execute(
            """INSERT INTO watch_log (item_id, watched_on, rating, liked, rewatch, source,
               source_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_id, watched_on, rating, liked_v, int(rewatch), source, source_key, now, now),
        )
        entry_id = cur.lastrowid
        if source == "manual":
            if rating is not None:
                self.conn.execute(
                    "UPDATE user_status SET rating = ?, manual_updated_at = ? WHERE item_id = ?",
                    (rating, now, item_id),
                )
            if liked is not None:
                self.set_liked(item_id, bool(liked), at=watched_on)
        self.conn.commit()
        self.recompute_user_status(item_id)
        return entry_id  # type: ignore[return-value]

    def get_watch_entry(self, entry_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM watch_log WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None

    def update_watch(self, entry_id: int, **fields: Any) -> None:
        """Edit a live log entry. Marks it edited so re-imports leave it alone."""
        allowed = {"watched_on", "rating", "liked", "rewatch"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"Cannot update fields: {sorted(bad)}")
        entry = self.get_watch_entry(entry_id)
        if not entry or entry["deleted_at"]:
            raise KeyError(f"No such log entry: {entry_id}")
        if "watched_on" in fields:
            _check_date(fields["watched_on"])
        if "rating" in fields:
            _check_rating(fields["rating"])
        for k in ("liked", "rewatch"):
            if k in fields and fields[k] is not None:
                fields[k] = int(bool(fields[k]))
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            self.conn.execute(
                f"UPDATE watch_log SET {set_clause}, edited = 1, updated_at = ? WHERE id = ?",
                [*fields.values(), _now(), entry_id],
            )
            self.conn.commit()
        self.recompute_user_status(entry["item_id"])

    def delete_watch(self, entry_id: int) -> None:
        """Soft-delete (tombstone) a log entry."""
        entry = self.get_watch_entry(entry_id)
        if not entry:
            raise KeyError(f"No such log entry: {entry_id}")
        self.conn.execute(
            "UPDATE watch_log SET deleted_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), entry_id),
        )
        self.conn.commit()
        self.recompute_user_status(entry["item_id"])

    def set_rating(self, item_id: int, rating: int | None) -> None:
        _check_rating(rating)
        self._ensure_status(item_id)
        self.conn.execute(
            "UPDATE user_status SET rating = ?, manual_updated_at = ? WHERE item_id = ?",
            (rating, _now(), item_id),
        )
        self.conn.commit()

    def set_liked(
        self, item_id: int, liked: bool, *, at: str | None = None, manual: bool = True
    ) -> None:
        self._ensure_status(item_id)
        self.conn.execute(
            "UPDATE user_status SET liked = ?, liked_date = ? WHERE item_id = ?",
            (int(liked), (at or date.today().isoformat()) if liked else None, item_id),
        )
        if manual:
            self.conn.execute(
                "UPDATE user_status SET manual_updated_at = ? WHERE item_id = ?", (_now(), item_id)
            )
        self.conn.commit()

    def recompute_user_status(self, item_id: int) -> None:
        """Derive seen/seen_date from live log entries.

        With live entries: seen=1, seen_date=latest. With none: seen=0 only if the user
        deleted entries (tombstones exist); items known only from watched.csv are untouched.
        """
        self._ensure_status(item_id)
        live = self.conn.execute(
            "SELECT MAX(watched_on) AS d, COUNT(*) AS n FROM watch_log"
            " WHERE item_id = ? AND deleted_at IS NULL",
            (item_id,),
        ).fetchone()
        if live["n"]:
            self.conn.execute(
                "UPDATE user_status SET seen = 1, seen_date = ? WHERE item_id = ?",
                (live["d"], item_id),
            )
        else:
            dead = self.conn.execute(
                "SELECT COUNT(*) AS n FROM watch_log WHERE item_id = ? AND deleted_at IS NOT NULL",
                (item_id,),
            ).fetchone()
            if dead["n"]:
                self.conn.execute(
                    "UPDATE user_status SET seen = 0, seen_date = NULL WHERE item_id = ?",
                    (item_id,),
                )
        self.conn.commit()

    # --- UI queries ---

    def get_watchlist_ids(self) -> list[int]:
        rows = self.conn.execute(
            """SELECT i.id FROM items i JOIN user_status us ON i.id = us.item_id
               WHERE us.on_watchlist = 1 ORDER BY i.id"""
        ).fetchall()
        return [r["id"] for r in rows]

    def get_heart_ids(self) -> list[int]:
        rows = self.conn.execute(
            "SELECT item_id FROM user_status WHERE liked = 1 ORDER BY item_id"
        ).fetchall()
        return [r["item_id"] for r in rows]

    def get_item_cards(self, item_ids: list[int]) -> dict[int, dict]:
        """Batch-build UI item cards (item + directors + status) keyed by item id."""
        if not item_ids:
            return {}
        ph = ",".join("?" for _ in item_ids)
        ids = tuple(item_ids)
        cards: dict[int, dict] = {}
        for r in self.conn.execute(
            f"""SELECT i.id, i.title, i.year, i.item_type, i.runtime_min,
                       us.seen, us.seen_date, us.on_watchlist, us.liked, us.rating,
                       us.watchlist_added_at,
                       (SELECT MAX(watched_on) FROM watch_log w
                        WHERE w.item_id = i.id AND w.deleted_at IS NULL) AS last_log
                FROM items i LEFT JOIN user_status us ON us.item_id = i.id
                WHERE i.id IN ({ph})""",
            ids,
        ):
            cards[r["id"]] = {
                "item_id": r["id"],
                "title": r["title"],
                "year": r["year"],
                "item_type": r["item_type"],
                "runtime_min": r["runtime_min"],
                "directors": [],
                "status": {
                    "seen": bool(r["seen"]),
                    "on_watchlist": bool(r["on_watchlist"]),
                    "liked": bool(r["liked"]),
                    "rating": r["rating"],
                    "last_watched_on": r["last_log"] or r["seen_date"],
                },
                "added_at": r["watchlist_added_at"],
            }
        for r in self.conn.execute(
            f"""SELECT c.item_id, p.id AS person_id, p.name FROM credits c
                JOIN people p ON p.id = c.person_id
                WHERE c.role = 'Director' AND c.item_id IN ({ph}) ORDER BY p.name""",
            ids,
        ):
            if r["item_id"] in cards:
                cards[r["item_id"]]["directors"].append(
                    {"person_id": r["person_id"], "name": r["name"]}
                )
        return cards

    def get_item_card(self, item_id: int) -> dict | None:
        return self.get_item_cards([item_id]).get(item_id)

    def get_item_sources(self, item_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT source FROM documents WHERE item_id = ? ORDER BY source", (item_id,)
        ).fetchall()
        return [r["source"] for r in rows]

    def find_items_by_title(self, q: str, limit: int = 10, item_type: str = "film") -> list[dict]:
        q = q.strip()
        if not q:
            return []
        like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = self.conn.execute(
            """SELECT id FROM items WHERE item_type = ? AND
               (title LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\')
               ORDER BY (title LIKE ? ESCAPE '\\') DESC, year DESC LIMIT ?""",
            (item_type, f"{like}%", f"%{like}%", f"{like}%", limit),
        ).fetchall()
        cards = self.get_item_cards([r["id"] for r in rows])
        return [cards[r["id"]] for r in rows]

    def get_watchlist(
        self,
        *,
        runtime_max: int | None = None,
        decade: int | None = None,
        q: str | None = None,
        sort: str = "added",
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        """Watchlist cards. Items with unknown runtime are excluded under runtime_max."""
        sql = """SELECT i.id FROM items i JOIN user_status us ON us.item_id = i.id
                 WHERE us.on_watchlist = 1 AND i.item_type = 'film'"""
        params: list[Any] = []
        if runtime_max is not None:
            sql += " AND i.runtime_min IS NOT NULL AND i.runtime_min <= ?"
            params.append(runtime_max)
        if decade is not None:
            sql += " AND i.year >= ? AND i.year < ?"
            params.extend([decade, decade + 10])
        if q:
            clause, qparams = _title_or_director(q)
            sql += clause
            params.extend(qparams)
        order = {
            "added": "us.watchlist_added_at DESC, i.id DESC",
            "runtime": "i.runtime_min IS NULL, i.runtime_min ASC, i.id",
            "year": "i.year DESC, i.id",
            "title": "i.title COLLATE NOCASE",
        }.get(sort, "us.watchlist_added_at DESC, i.id DESC")
        ids = [r["id"] for r in self.conn.execute(sql + f" ORDER BY {order}", params)]
        total = len(ids)
        ids = ids[offset:] if limit is None else ids[offset:offset + limit]
        cards = self.get_item_cards(ids)
        return total, [cards[i] for i in ids]

    def watchlist_summary(self, short_max: int = 90) -> dict:
        """Count, total minutes and number of films at or under ``short_max`` minutes."""
        row = self.conn.execute(
            """SELECT COUNT(*) AS n, COALESCE(SUM(i.runtime_min), 0) AS minutes,
                      COALESCE(SUM(CASE WHEN i.runtime_min <= ? THEN 1 ELSE 0 END), 0) AS short
               FROM items i JOIN user_status us ON us.item_id = i.id
               WHERE us.on_watchlist = 1 AND i.item_type = 'film'""",
            (short_max,),
        ).fetchone()
        return {"count": row["n"], "total_minutes": row["minutes"], "short_count": row["short"]}

    def get_watch_log(
        self,
        *,
        year: int | None = None,
        month: int | None = None,
        min_rating: int | None = None,
        q: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[int, list[dict], dict]:
        """Live log entries (newest first) with a summary over the whole filtered set."""
        sql = """SELECT w.*, i.runtime_min FROM watch_log w JOIN items i ON i.id = w.item_id
                 WHERE w.deleted_at IS NULL"""
        params: list[Any] = []
        if year is not None:
            sql += " AND substr(w.watched_on, 1, 4) = ?"
            params.append(f"{year:04d}")
        if month is not None:
            sql += " AND substr(w.watched_on, 6, 2) = ?"
            params.append(f"{month:02d}")
        if min_rating is not None:
            sql += " AND w.rating >= ?"
            params.append(min_rating)
        if q:
            clause, qparams = _title_or_director(q)
            sql += clause
            params.extend(qparams)
        rows = self.conn.execute(sql + " ORDER BY w.watched_on DESC, w.id DESC", params).fetchall()

        rated = [r["rating"] for r in rows if r["rating"] is not None]
        by_month: dict[str, int] = {}
        for r in rows:
            by_month[r["watched_on"][:7]] = by_month.get(r["watched_on"][:7], 0) + 1
        summary = {
            "count": len(rows),
            "avg_rating": round(sum(rated) / len(rated), 2) if rated else None,
            "total_minutes": sum(r["runtime_min"] or 0 for r in rows),
            "by_month": [{"month": m, "count": c} for m, c in sorted(by_month.items(), reverse=True)],
        }
        page = rows[offset:] if limit is None else rows[offset:offset + limit]
        cards = self.get_item_cards([r["item_id"] for r in page])
        entries = [self._entry_dict(r, cards[r["item_id"]]) for r in page]
        return len(rows), entries, summary

    @staticmethod
    def _entry_dict(row: Any, card: dict) -> dict:
        return {
            "entry_id": row["id"],
            "item": card,
            "watched_on": row["watched_on"],
            "rating": row["rating"],
            "liked": None if row["liked"] is None else bool(row["liked"]),
            "rewatch": bool(row["rewatch"]),
            "source": row["source"],
        }

    def get_watch_entry_view(self, entry_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM watch_log WHERE id = ? AND deleted_at IS NULL", (entry_id,)
        ).fetchone()
        if not row:
            return None
        return self._entry_dict(row, self.get_item_card(row["item_id"]))

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
        tables = [
            "items", "user_status", "documents", "chunks", "people", "credits", "eval_runs",
            "watch_log",
        ]
        result = {}
        for t in tables:
            row = self.conn.execute(f"SELECT COUNT(*) as c FROM {t}").fetchone()
            result[t] = row["c"]
        return result
