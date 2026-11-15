"""Domain errors raised by the store."""

from __future__ import annotations


class NotFoundError(KeyError):
    """A requested row does not exist (the web layer maps this to 404)."""


class InvalidInputError(ValueError):
    """Caller-supplied data is invalid (the web layer maps this to 422)."""
