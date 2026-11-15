"""Raw-response cache registry and the match review queue."""

from __future__ import annotations

import json


class IngestMetaMixin:
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
