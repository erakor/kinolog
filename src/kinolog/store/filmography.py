"""Full TMDB filmographies: ``tmdb_movies`` and ``person_filmography`` (migration 005)."""

from __future__ import annotations

import json
from datetime import UTC, datetime


class FilmographyMixin:
    def upsert_tmdb_movie(
        self,
        tmdb_id: int,
        title: str,
        *,
        original_title: str | None = None,
        release_date: str | None = None,
        year: int | None = None,
        runtime: int | None = None,
        status: str | None = None,
        is_video: bool = False,
        genre_ids: list[int] | None = None,
        commit: bool = True,
    ) -> None:
        """Insert or replace one TMDB movie's facts. A runtime of 0 is stored as NULL."""
        self.conn.execute(
            """INSERT OR REPLACE INTO tmdb_movies
               (tmdb_id, title, original_title, release_date, year, runtime, status,
                is_video, genre_ids, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tmdb_id, title, original_title, release_date or None, year, runtime or None,
                status, int(is_video), json.dumps(list(genre_ids or [])),
                datetime.now(UTC).isoformat(),
            ),
        )
        if commit:
            self.conn.commit()

    def set_person_filmography(
        self, person_id: int, tmdb_ids: list[int], job: str = "Director", *, commit: bool = True
    ) -> None:
        """Add the person's credits for ``job``. Idempotent; never removes existing rows."""
        self.conn.executemany(
            "INSERT OR IGNORE INTO person_filmography (person_id, tmdb_id, job) VALUES (?, ?, ?)",
            [(person_id, t, job) for t in dict.fromkeys(tmdb_ids)],
        )
        if commit:
            self.conn.commit()
