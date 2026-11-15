"""Watchlist, watch log, ratings and likes."""

from __future__ import annotations

from datetime import date
from typing import Any

from kinolog.store.errors import InvalidInputError, NotFoundError
from kinolog.store.util import _check_date, _check_rating, _now


class UserStateMixin:
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

    def _ensure_status(self, item_id: int):
        if not self.conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone():
            raise NotFoundError(f"No such item: {item_id}")
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
        watched_on = _check_date(watched_on)
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
            raise InvalidInputError(f"Cannot update fields: {sorted(bad)}")
        entry = self.get_watch_entry(entry_id)
        if not entry or entry["deleted_at"]:
            raise NotFoundError(f"No such log entry: {entry_id}")
        if "watched_on" in fields:
            fields["watched_on"] = _check_date(fields["watched_on"])
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
            raise NotFoundError(f"No such log entry: {entry_id}")
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
