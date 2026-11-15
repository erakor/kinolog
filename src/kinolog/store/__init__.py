"""Persistence layer: the ``Database`` facade over SQLite (FTS5, optional sqlite-vec)."""

from kinolog.store.database import Database
from kinolog.store.errors import InvalidInputError, NotFoundError
from kinolog.store.util import chunked, content_hash

__all__ = ["Database", "InvalidInputError", "NotFoundError", "chunked", "content_hash"]
