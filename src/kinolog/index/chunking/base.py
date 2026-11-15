"""Chunking strategy protocol and registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from kinolog.domain import Chunk


class ChunkStrategy(Protocol):
    """A strategy turns one document's text into ordered chunks."""

    def __call__(self, text: str) -> list[Chunk]: ...


STRATEGIES: dict[str, ChunkStrategy] = {}


def register(name: str) -> Callable[[ChunkStrategy], ChunkStrategy]:
    """Register a strategy under the name stored on each chunk row."""

    def decorator(fn: ChunkStrategy) -> ChunkStrategy:
        if name in STRATEGIES:
            raise ValueError(f"Chunking strategy {name!r} is already registered")
        STRATEGIES[name] = fn
        return fn

    return decorator
