"""Embedding model protocol and registry."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import numpy as np


class EmbeddingModel(Protocol):
    """Protocol for embedding models."""

    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray: ...


# Model name (as used by `--model` and in vec_<name> table names) -> constructor taking `device`.
EMBEDDERS: dict[str, Callable[..., EmbeddingModel]] = {}


def register(name: str) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        if name in EMBEDDERS:
            raise ValueError(f"Embedding model {name!r} is already registered")
        EMBEDDERS[name] = cls
        return cls

    return decorator
