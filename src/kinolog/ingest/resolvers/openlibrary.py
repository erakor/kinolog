"""Open Library resolver: match book items to Open Library works/editions."""

from __future__ import annotations

import json
import logging
import urllib.parse

from kinolog.config import OPENLIBRARY_CACHE_DIR
from kinolog.store import Database

logger = logging.getLogger(__name__)

CACHE_DIR = OPENLIBRARY_CACHE_DIR


class OpenLibraryResolver:
    """Resolve book items to Open Library identifiers using ISBN or Title + Author."""

    def __init__(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _fetch_url(self, url: str) -> dict:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": "Kinolog/1.0 (personal-film-and-book-index)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def resolve_by_isbn(self, isbn: str) -> dict | None:
        """Lookup by ISBN."""
        clean_isbn = isbn.replace("-", "").strip()
        cache_path = CACHE_DIR / f"isbn_{clean_isbn}.json"

        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        url = f"https://openlibrary.org/isbn/{clean_isbn}.json"
        try:
            data = self._fetch_url(url)
            cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            return data.get("docs", [])

        url = f"https://openlibrary.org/search.json?{query_str}&limit=5"
        try:
            data = self._fetch_url(url)
            cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data.get("docs", [])
        except Exception as e:
            logger.warning("Open Library search failed for '%s' by '%s': %s", title, author, e)
            return []

    def resolve_item(self, db: Database, item_id: int) -> dict | None:
        """Resolve a book item to Open Library."""
        item = db.get_item(item_id)
        if not item or item.get("item_type") != "book":
            return None

        if item.get("openlibrary_id"):
            return {"openlibrary_id": item["openlibrary_id"]}

        # 1. Try ISBN if available
        if item.get("isbn"):
            data = self.resolve_by_isbn(item["isbn"])
            if data:
                olid = data.get("key")
                title = data.get("title", item["title"])
                db.execute(
                    "UPDATE items SET openlibrary_id = ?, match_confidence = 1.0, match_status = 'auto' WHERE id = ?",
                    (olid, item_id),
                )
                db.conn.commit()
                return {"openlibrary_id": olid, "title": title}

        # 2. Try Title + Author
        title = item["title"]
        author = None
        if item.get("original_title") and " — " in item["original_title"]:
            author = item["original_title"].split(" — ", 1)[1]

        candidates = self.search_by_title_author(title, author)
        if not candidates:
            db.queue_for_review(item_id, [], "no_openlibrary_results")
            db.execute("UPDATE items SET match_status = 'queued' WHERE id = ?", (item_id,))
            db.conn.commit()
            return None

        # Check top candidate
        top = candidates[0]
        top_title = top.get("title", "")
        olid = top.get("key")

        # Auto-match if title is very close
        if top_title.lower().strip() == title.lower().strip():
            db.execute(
                "UPDATE items SET openlibrary_id = ?, match_confidence = 0.85, match_status = 'auto' WHERE id = ?",
                (olid, item_id),
            )
            db.conn.commit()
            return {"openlibrary_id": olid, "title": top_title}

        # Queue ambiguous
        candidates_json = [
            {"openlibrary_id": c.get("key"), "title": c.get("title"), "author_name": c.get("author_name")}
            for c in candidates[:5]
        ]
        db.queue_for_review(item_id, candidates_json, "ambiguous_openlibrary")
        db.execute("UPDATE items SET match_status = 'queued' WHERE id = ?", (item_id,))
        db.conn.commit()
        return None
