"""BAAI/bge-m3 via sentence-transformers."""

from __future__ import annotations

import logging

import numpy as np

from kinolog.index.embedding.base import register

logger = logging.getLogger(__name__)


@register("bge_m3")
class BGE_M3:
    """BAAI/bge-m3 via sentence-transformers (1024-dim, multilingual)."""

    def __init__(self, device: str | None = None):
        from sentence_transformers import SentenceTransformer

        self._name = "bge_m3"
        self._dim = 1024
        self._device = device

        logger.info("Loading bge-m3 model...")
        self.model = SentenceTransformer("BAAI/bge-m3", device=device)
        logger.info("bge-m3 loaded on %s", self.model.device)

    @property
    def name(self) -> str:
        return self._name

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype=np.float32)
