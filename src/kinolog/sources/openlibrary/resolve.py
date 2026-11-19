"""Open Library resolver: match book items to Open Library works/editions."""

from __future__ import annotations

import logging

from kinolog.sources.openlibrary.client import OpenLibraryClient
from kinolog.store import Database

logger = logging.getLogger(__name__)


class OpenLibraryResolver:
    """Resolve book items to Open Library identifiers using ISBN or Title + Author."""

    def __init__(self, client: OpenLibraryClient | None = None):
        self.client = client or OpenLibraryClient()

    def resolve_item(self, db: Database, item_id: int) -> dict | None:
        """Resolve a book item to Open Library."""
        item = db.get_item(item_id)
        if not item or item.get("item_type") != "book":
            return None

        if item.get("openlibrary_id"):
            return {"openlibrary_id": item["openlibrary_id"]}

        # 1. Try ISBN if available
        if item.get("isbn"):
            data = self.client.resolve_by_isbn(item["isbn"])
            if data:
                olid = data.get("key")
                title = data.get("title", item["title"])
                db.set_match(item_id, openlibrary_id=olid, confidence=1.0)
                return {"openlibrary_id": olid, "title": title}

        # 2. Try Title + Author
        title = item["title"]
        author = None
        if item.get("original_title") and " — " in item["original_title"]:
            author = item["original_title"].split(" — ", 1)[1]

        candidates = self.client.search_by_title_author(title, author)
        if not candidates:
            db.queue_for_review(item_id, [], "no_openlibrary_results")
            db.mark_queued(item_id)
            return None

        # Check top candidate
        top = candidates[0]
        top_title = top.get("title", "")
        olid = top.get("key")

        # Auto-match if title is very close
        if top_title.lower().strip() == title.lower().strip():
            db.set_match(item_id, openlibrary_id=olid, confidence=0.85)
            return {"openlibrary_id": olid, "title": top_title}

        # Queue ambiguous
        candidates_json = [
            {
                "openlibrary_id": c.get("key"),
                "title": c.get("title"),
                "author_name": c.get("author_name"),
            }
            for c in candidates[:5]
        ]
        db.queue_for_review(item_id, candidates_json, "ambiguous_openlibrary")
        db.mark_queued(item_id)
        return None
