"""Columns added after the first schema version.

Python rather than SQL because every database that existed before migrations were introduced
already has these columns while reporting ``user_version = 0``; each column is only added if
it is missing.
"""

from __future__ import annotations

import sqlite3

# (table, column, declaration)
ADDED_COLUMNS = [
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
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column in cols:
        return False
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
    return True


def upgrade(conn: sqlite3.Connection) -> None:
    for table, column, decl in ADDED_COLUMNS:
        ensure_column(conn, table, column, decl)
