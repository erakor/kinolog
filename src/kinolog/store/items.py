"""Item CRUD and lookup."""

from __future__ import annotations

from typing import Any


class ItemsMixin:
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

    def get_item_sources(self, item_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT source FROM documents WHERE item_id = ? ORDER BY source", (item_id,)
        ).fetchall()
        return [r["source"] for r in rows]

    def set_match(
        self,
        item_id: int,
        *,
        tmdb_id: int | None = None,
        openlibrary_id: str | None = None,
        confidence: float,
        status: str = "auto",
    ) -> None:
        """Record a resolved external id (TMDB when ``tmdb_id`` is given, else Open Library)."""
        if tmdb_id is not None:
            column, value = "tmdb_id", tmdb_id
        else:
            column, value = "openlibrary_id", openlibrary_id
        self.conn.execute(
            f"UPDATE items SET {column} = ?, match_status = ?, match_confidence = ? WHERE id = ?",
            (value, status, confidence, item_id),
        )
        self.conn.commit()

    def mark_queued(self, item_id: int) -> None:
        """Flag an item as waiting in the match review queue."""
        self.conn.execute("UPDATE items SET match_status = 'queued' WHERE id = ?", (item_id,))
        self.conn.commit()

    def set_item_facts(
        self,
        item_id: int,
        *,
        runtime_min: int | None = None,
        is_tv: bool | None = None,
        original_title: str | None = None,
        commit: bool = True,
    ) -> None:
        """Set the given structured facts (None leaves a field alone).

        Pass ``commit=False`` inside a batch and commit once at the end.
        """
        fields = []
        if original_title is not None:
            fields.append(("original_title", original_title))
        if runtime_min is not None:
            fields.append(("runtime_min", int(runtime_min)))
        if is_tv is not None:
            fields.append(("is_tv", int(is_tv)))
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name, _ in fields)
        self.conn.execute(
            f"UPDATE items SET {assignments} WHERE id = ?",
            (*[value for _, value in fields], item_id),
        )
        if commit:
            self.conn.commit()

    def set_wikidata_id_if_missing(self, item_id: int, wikidata_id: str) -> None:
        self.conn.execute(
            "UPDATE items SET wikidata_id = ? WHERE id = ? AND wikidata_id IS NULL",
            (wikidata_id, item_id),
        )
        self.conn.commit()
