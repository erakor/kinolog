"""TMDB HTTP client: throttled requests plus the on-disk cache of movie details."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx

from kinolog.config import TMDB_CACHE_DIR, get_tmdb_api_key
from kinolog.sources.http_cache import read_json, write_json

logger = logging.getLogger(__name__)

TMDB_BASE = "https://api.themoviedb.org/3"
CACHE_DIR = TMDB_CACHE_DIR


def tmdb_cache_path(tmdb_id: int, cache_dir: Path | None = None) -> Path:
    """Disk cache file for a TMDB movie details response."""
    return Path(cache_dir or CACHE_DIR) / f"movie_{tmdb_id}.json"


def person_credits_cache_path(tmdb_person_id: int, cache_dir: Path | None = None) -> Path:
    """Disk cache file for a TMDB person's movie credits response."""
    return Path(cache_dir or CACHE_DIR) / f"person_{tmdb_person_id}_movie_credits.json"


class TMDBClient:
    """Thin client for the TMDB API (search, movie details and person credits)."""

    def __init__(self, api_key: str | None = None, rate_limit: float = 0.25):
        self.api_key = api_key or get_tmdb_api_key()
        self.rate_limit = rate_limit  # seconds between requests
        self._last_request = 0.0
        self.client = httpx.Client(
            base_url=TMDB_BASE,
            params={"api_key": self.api_key},
            timeout=30.0,
        )
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _throttle(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def _get(self, path: str, **params) -> dict:
        self._throttle()
        resp = self.client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    def search(self, title: str, year: int | None = None, language: str = "en-US") -> list[dict]:
        """Search TMDB for a movie by title, optionally constrained by year."""
        params = {"query": title, "language": language}
        if year:
            params["year"] = str(year)
        data = self._get("/search/movie", **params)
        return data.get("results", [])

    def get_details(self, tmdb_id: int) -> dict:
        """Get full movie details with credits, keywords, and alternative titles."""
        cache_path = tmdb_cache_path(tmdb_id)
        if cache_path.exists():
            return read_json(cache_path)

        data = self._get(
            f"/movie/{tmdb_id}",
            append_to_response="credits,keywords,external_ids,alternative_titles,translations",
        )
        write_json(cache_path, data)
        return data

    def get_person_movie_credits(self, tmdb_person_id: int, refresh: bool = False) -> dict:
        """A person's movie credits (cast and crew), from the disk cache unless ``refresh``."""
        cache_path = person_credits_cache_path(tmdb_person_id)
        if not refresh and cache_path.exists():
            return read_json(cache_path)

        data = self._get(f"/person/{tmdb_person_id}/movie_credits")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(cache_path, data)
        return data

    def close(self):
        self.client.close()
