"""Third-party scores (OMDb: IMDb, Rotten Tomatoes, Metacritic)."""

from __future__ import annotations

from kinolog.store.util import _now, chunked


class RatingsMixin:
    def set_external_ratings(self, item_id: int, provider: str, ratings: list[dict]) -> None:
        """Replace an item's ratings from one provider (sources it no longer reports are dropped).

        Each rating is {"source", "score" (0..100), "raw", "votes"}. Does not commit, so
        batch callers commit once.
        """
        now = _now()
        self.conn.execute(
            "DELETE FROM external_ratings WHERE item_id = ? AND provider = ?", (item_id, provider)
        )
        self.conn.executemany(
            """INSERT INTO external_ratings
               (item_id, source, score, raw, votes, provider, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    item_id,
                    r["source"],
                    float(r["score"]),
                    r.get("raw"),
                    r.get("votes"),
                    provider,
                    now,
                )
                for r in ratings
            ],
        )

    def get_external_ratings(self, item_ids: list[int]) -> dict[int, list[dict]]:
        """Ratings per item, in display order (IMDb, Rotten Tomatoes, Metacritic, others)."""
        out: dict[int, list[dict]] = {i: [] for i in item_ids}
        for part in chunked(list(item_ids)):
            ph = ",".join("?" for _ in part)
            for r in self.conn.execute(
                f"""SELECT item_id, source, score, raw, votes FROM external_ratings
                    WHERE item_id IN ({ph})
                    ORDER BY item_id, CASE source WHEN 'imdb' THEN 0
                        WHEN 'rotten_tomatoes' THEN 1 WHEN 'metacritic' THEN 2 ELSE 3 END,
                        source""",
                tuple(part),
            ):
                out[r["item_id"]].append(
                    {
                        "source": r["source"],
                        "score": r["score"],
                        "raw": r["raw"],
                        "votes": r["votes"],
                    }
                )
        return out
