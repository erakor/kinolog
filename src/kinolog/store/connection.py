"""Connection handling: opening SQLite, loading sqlite-vec, transactions."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from kinolog.config import DEFAULT_DB_PATH
from kinolog.store import migrations
from kinolog.store.migrations.m002_added_columns import ensure_column

logger = logging.getLogger(__name__)


class ConnectionBase:
    """SQLite connection with optional sqlite-vec support."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH, check_same_thread: bool = True):
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
        migrations.apply(self.conn)

    def _try_load_vec(self) -> bool:
        """Try to load the sqlite-vec extension."""
        try:
            import sqlite_vec

            # sqlite-vec >= 0.1.9 no longer enables extension loading itself.
            self.conn.enable_load_extension(True)
            try:
                sqlite_vec.load(self.conn)
            finally:
                self.conn.enable_load_extension(False)
            logger.info("sqlite-vec loaded successfully")
            return True
        except (ImportError, Exception) as e:
            logger.warning("sqlite-vec not available: %s", e)
            return False

    @property
    def vec_available(self) -> bool:
        return self._vec_available

    def _ensure_column(self, table: str, column: str, decl: str) -> bool:
        """Add a column if missing. Returns True if added."""
        added = ensure_column(self.conn, table, column, decl)
        self.conn.commit()
        return added

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
