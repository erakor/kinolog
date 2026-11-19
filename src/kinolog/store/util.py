"""Small helpers shared by the store modules."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

from kinolog.store.errors import InvalidInputError


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def chunked(items: list, size: int = 500):
    """Yield slices so IN (...) lists stay under SQLite's variable limit (999 on old builds)."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _check_date(value: str) -> str:
    """Validate a date and return it as YYYY-MM-DD (rejects ISO basic/week forms' raw text)."""
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as e:
        raise InvalidInputError(f"Invalid date (expected YYYY-MM-DD): {value!r}") from e


def _check_rating(rating: int | None) -> int | None:
    if rating is None:
        return None
    if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 10:
        raise InvalidInputError(f"Rating must be an integer 1..10 (half-stars), got {rating!r}")
    return rating


def _title_or_director(q: str) -> tuple[str, list[str]]:
    """SQL fragment (alias i) matching a title or a director name, plus its params."""
    like = f"%{q.strip()}%"
    return (
        """ AND (i.title LIKE ? OR EXISTS (SELECT 1 FROM credits c
               JOIN people p ON p.id = c.person_id
               WHERE c.item_id = i.id AND c.role = 'Director' AND p.name LIKE ?))""",
        [like, like],
    )


def content_hash(text: str) -> str:
    """SHA-256 hex digest of text, used for change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
