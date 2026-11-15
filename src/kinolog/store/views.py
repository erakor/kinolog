"""Read models for the interfaces: item cards, watchlist, watch log, stats."""

from __future__ import annotations

from typing import Any

from kinolog.store.util import _title_or_director, chunked


class ViewsMixin:
    def get_item_cards(self, item_ids: list[int]) -> dict[int, dict]:
        """Batch-build UI item cards (item + directors + status) keyed by item id."""
        cards: dict[int, dict] = {}
        for part in chunked(list(item_ids)):
            self._fill_item_cards(part, cards)
        return cards

    def _fill_item_cards(self, item_ids: list[int], cards: dict[int, dict]) -> None:
        ph = ",".join("?" for _ in item_ids)
        ids = tuple(item_ids)
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

    def get_item_card(self, item_id: int) -> dict | None:
        return self.get_item_cards([item_id]).get(item_id)

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
