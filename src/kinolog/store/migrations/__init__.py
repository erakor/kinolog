"""Numbered schema migrations.

Files are named ``mNNN_description.sql`` or ``mNNN_description.py`` (a Python migration defines
``upgrade(conn)``). ``PRAGMA user_version`` holds the number of the last applied migration.

Rules:
- To change the schema, add a new numbered file. Never edit a migration that has been applied.
- Migrations 001 to 003 are idempotent because databases created before migrations existed have
  ``user_version = 0`` but already contain everything they create. From 004 on, a migration can
  assume the previous state and need not be idempotent.
- Per-model vector tables (``vec_<model>``) are created on demand, not by migrations.
"""

from __future__ import annotations

import importlib
import re
import sqlite3
from dataclasses import dataclass
from importlib import resources

_NAME = re.compile(r"^m(\d{3})_[a-z0-9_]+\.(sql|py)$")


@dataclass(frozen=True)
class Migration:
    number: int
    name: str
    kind: str  # "sql" or "py"


def discover() -> list[Migration]:
    """All migrations shipped with the package, in order. Raises on gaps or duplicates."""
    found = []
    for entry in resources.files(__package__).iterdir():
        m = _NAME.match(entry.name)
        if m:
            found.append(Migration(int(m.group(1)), entry.name, m.group(2)))
    found.sort(key=lambda mig: mig.number)
    numbers = [mig.number for mig in found]
    if numbers != list(range(1, len(numbers) + 1)):
        raise RuntimeError(f"Migration numbers must be 1..N without gaps, got {numbers}")
    return found


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def latest_version() -> int:
    return len(discover())


def apply(conn: sqlite3.Connection) -> int:
    """Run every pending migration in order. Returns the resulting ``user_version``."""
    version = current_version(conn)
    for mig in discover():
        if mig.number <= version:
            continue
        if conn.in_transaction:
            conn.commit()
        if mig.kind == "sql":
            # executescript commits implicitly, so a crash between the script and the version
            # bump leaves the migration to run again; 001-003 are idempotent for that reason.
            sql = resources.files(__package__).joinpath(mig.name).read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {mig.number}")
            conn.commit()
        else:
            module = importlib.import_module(f"{__package__}.{mig.name[:-3]}")
            conn.execute("BEGIN")
            try:
                module.upgrade(conn)
                conn.execute(f"PRAGMA user_version = {mig.number}")
            except BaseException:
                conn.rollback()
                raise
            conn.commit()
        version = mig.number
    return version
