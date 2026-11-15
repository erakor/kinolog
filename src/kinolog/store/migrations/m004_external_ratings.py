"""Third-party ratings: the external_ratings table and items.imdb_id.

Python and idempotent (IF NOT EXISTS / ensure_column) because databases that ran the pre-migration
OMDb code already have both while reporting an older ``user_version``.
"""

from __future__ import annotations

import sqlite3

from kinolog.store.migrations.m002_added_columns import ensure_column


def upgrade(conn: sqlite3.Connection) -> None:
    ensure_column(conn, "items", "imdb_id", "TEXT")
    # score is normalized to 0..100; raw keeps the provider's string (e.g. "8.1/10", "94%").
    conn.execute(
        """CREATE TABLE IF NOT EXISTS external_ratings (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    score REAL NOT NULL,
    raw TEXT,
    votes INTEGER,
    provider TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (item_id, source)
)"""
    )
