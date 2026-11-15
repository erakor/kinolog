"""Chunking strategies for documents.

``STRATEGIES`` maps a strategy name (stored on each chunk row) to a function turning text into
chunks. Variants live one per module and register themselves on import; they are all imported
here so the registry is complete whichever module a caller imports first.
"""

from kinolog.index.chunking import fixed, section, whole  # noqa: F401  (registers strategies)
from kinolog.index.chunking.base import STRATEGIES, ChunkStrategy, register
from kinolog.index.chunking.fixed import chunk_fixed_window
from kinolog.index.chunking.runner import chunk_all_documents, chunk_document
from kinolog.index.chunking.section import chunk_by_section
from kinolog.index.chunking.whole import chunk_whole_document

__all__ = [
    "STRATEGIES",
    "ChunkStrategy",
    "chunk_all_documents",
    "chunk_by_section",
    "chunk_document",
    "chunk_fixed_window",
    "chunk_whole_document",
    "register",
]
