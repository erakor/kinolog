"""Open Library HTTP client: ISBN and title/author lookups with an on-disk cache."""

from __future__ import annotations

import logging
import urllib.parse

from kinolog.config import OPENLIBRARY_CACHE_DIR
from kinolog.sources.http_cache import fetch_json, read_json, write_json

logger = logging.getLogger(__name__)

CACHE_DIR = OPENLIBRARY_CACHE_DIR
USER_AGENT = "Kinolog/1.0 (personal-film-and-book-index)"


class OpenLibraryClient:
    """Look up books on Open Library by ISBN or by title and author."""

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _fetch_url(self, url: str) -> dict:
        return fetch_json(url, USER_AGENT)

    def resolve_by_isbn(self, isbn: str) -> dict | None:
        """Lookup by ISBN."""
        clean_isbn = isbn.replace("-", "").strip()
        cache_path = CACHE_DIR / f"isbn_{clean_isbn}.json"

        if cache_path.exists():
            return read_json(cache_path)

        url = f"https://openlibrary.org/isbn/{clean_isbn}.json"
        try:
            data = self._fetch_url(url)
            write_json(cache_path, data)
            return data
        except Exception as e:
            logger.debug("Open Library ISBN lookup failed for %s: %s", isbn, e)
            return None

    def search_by_title_author(self, title: str, author: str | None = None) -> list[dict]:
        """Search by title and optional author."""
        query_params = {"title": title}
        if author:
            query_params["author"] = author

        query_str = urllib.parse.urlencode(query_params)
        safe_key = urllib.parse.quote(f"{title}_{author or ''}", safe="")
        cache_path = CACHE_DIR / f"search_{safe_key}.json"

        if cache_path.exists():
            data = read_json(cache_path)
            return data.get("docs", [])

        url = f"https://openlibrary.org/search.json?{query_str}&limit=5"
        try:
            data = self._fetch_url(url)
            write_json(cache_path, data)
            return data.get("docs", [])
        except Exception as e:
            logger.warning("Open Library search failed for '%s' by '%s': %s", title, author, e)
            return []
