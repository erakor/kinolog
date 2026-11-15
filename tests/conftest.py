"""Shared fixtures and small factories.

``db`` is an in-memory database. Use ``make_film`` / ``make_document`` where they shorten a
fixture; tests with specialised setups keep building their own data.
"""

import pytest

from kinolog.store import Database


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


def make_film(db, title, year=2000, *, runtime_min=None, **status):
    """Insert a film and return its item id. ``status`` fields go to ``user_status``."""
    item_id = db.upsert_item("film", title, year, runtime_min=runtime_min)
    if status:
        db.upsert_user_status(item_id, **status)
    return item_id


def make_document(db, item_id, text, source="tmdb", lang="en"):
    """Insert a document for an item and return its id."""
    return db.upsert_document(item_id, source, lang, text)
