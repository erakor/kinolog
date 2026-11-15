"""People and credits."""

from __future__ import annotations


class PeopleMixin:
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
