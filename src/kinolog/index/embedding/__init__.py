"""Embedding models and the chunk embedding runner.

``EMBEDDERS`` maps a model name to its class; variants register themselves on import and are
all imported here so the registry is complete whichever module a caller imports first.
"""

from kinolog.index.embedding import bge_m3, e5  # noqa: F401  (registers models)
from kinolog.index.embedding.base import EMBEDDERS, EmbeddingModel, register
from kinolog.index.embedding.bge_m3 import BGE_M3
from kinolog.index.embedding.e5 import MultilingualE5
from kinolog.index.embedding.runner import embed_chunks

__all__ = [
    "BGE_M3",
    "EMBEDDERS",
    "EmbeddingModel",
    "MultilingualE5",
    "embed_chunks",
    "register",
]
