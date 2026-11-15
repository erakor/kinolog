"""Taste ranker protocol and registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from kinolog.store import Database

if TYPE_CHECKING:
    from kinolog.taste.scores import TasteScore


class Ranker(Protocol):
    """Scores candidate items by similarity to the hearted items' embeddings."""

    def __call__(
        self, db: Database, candidate_ids: list[int], heart_ids: list[int], **kwargs
    ) -> list[TasteScore]: ...


RANKERS: dict[str, Ranker] = {}


def register(name: str) -> Callable[[Ranker], Ranker]:
    def decorator(fn: Ranker) -> Ranker:
        if name in RANKERS:
            raise ValueError(f"Taste ranker {name!r} is already registered")
        RANKERS[name] = fn
        return fn

    return decorator
