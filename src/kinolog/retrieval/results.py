"""Search result type shared by every retrieval mode."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchResult:
    item_id: int
    chunk_id: int | None = None
    score: float = 0.0
    title: str = ""
    year: int | None = None
    chunk_text: str = ""
    source: str = ""  # "vector", "bm25", "rrf"
    metadata: dict = field(default_factory=dict)
