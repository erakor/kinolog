"""Whole-document strategy: one chunk per document."""

from __future__ import annotations

from kinolog.domain import Chunk
from kinolog.index.chunking.base import register
from kinolog.index.chunking.runner import _estimate_tokens


def chunk_whole_document(text: str) -> list[Chunk]:
    """One chunk per document — baseline strategy."""
    return [Chunk(text=text.strip(), ord=0, token_count=_estimate_tokens(text))]


register("whole")(chunk_whole_document)
