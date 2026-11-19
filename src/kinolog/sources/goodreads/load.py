"""Goodreads CSV loader."""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

from kinolog.store import Database

logger = logging.getLogger(__name__)

EXPECTED_COLS = {
    "Book Id",
    "Title",
    "Author",
    "ISBN",
    "ISBN13",
    "My Rating",
    "Exclusive Shelf",
    "Date Read",
    "Date Added",
    "Bookshelves",
}


def _clean_isbn(raw: str | None) -> str | None:
    """Strip the ='...' wrapping Goodreads puts on ISBNs."""
    if not raw:
        return None
    # ='0451524934' or ="0451524934"
    cleaned = re.sub(r'[="\']+', "", raw).strip()
    return cleaned if cleaned else None


def _parse_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if rows:
        cols = set(rows[0].keys())
        missing = EXPECTED_COLS - cols
        if missing:
            logger.warning("Goodreads CSV missing expected columns: %s (has: %s)", missing, cols)
    return rows


def load_goodreads(db: Database, csv_path: str | Path) -> dict:
    """
    Load Goodreads export into the database.

    Returns stats dict with counts.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Goodreads CSV not found: {csv_path}")

    rows = _parse_csv(csv_path)
    stats = {"total": 0, "read": 0, "to_read": 0, "with_isbn": 0}

    for row in rows:
        title = (row.get("Title") or "").strip()
        if not title:
            continue

        author = (row.get("Author") or "").strip()
        isbn = _clean_isbn(row.get("ISBN"))
        isbn13 = _clean_isbn(row.get("ISBN13"))
        # Prefer ISBN-13
        best_isbn = isbn13 or isbn

        year_str = row.get("Original Publication Year") or row.get("Year Published")
        year = None
        if year_str:
            try:
                year = int(year_str.strip())
            except ValueError:
                pass

        shelf = (row.get("Exclusive Shelf") or "").strip()
        date_read = (row.get("Date Read") or "").strip() or None

        # Add author to title for better matching
        original_title = f"{title} — {author}" if author else title

        item_id = db.upsert_item(
            "book",
            title,
            year,
            original_title=original_title,
            isbn=best_isbn,
        )

        seen = 1 if shelf == "read" else 0
        on_watchlist = 1 if shelf == "to-read" else 0

        db.upsert_user_status(
            item_id,
            seen=seen,
            seen_date=date_read,
            on_watchlist=on_watchlist,
            source="goodreads",
        )

        stats["total"] += 1
        if seen:
            stats["read"] += 1
        if on_watchlist:
            stats["to_read"] += 1
        if best_isbn:
            stats["with_isbn"] += 1

    db.conn.commit()
    logger.info(
        "Loaded %d books (%d read, %d to-read, %d with ISBN)",
        stats["total"],
        stats["read"],
        stats["to_read"],
        stats["with_isbn"],
    )
    return stats
