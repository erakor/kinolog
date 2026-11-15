"""intfloat/multilingual-e5-base via sentence-transformers."""

from __future__ import annotations

import numpy as np

from kinolog.index.embedding.base import register


@register("multilingual_e5")
class MultilingualE5:
    """intfloat/multilingual-e5-base (768-dim) with query/passage prefixes."""

    def __init__(self, device: str | None = None):
        from sentence_transformers import SentenceTransformer

        self._name = "multilingual_e5"
        self._dim = 768
        self.model = SentenceTransformer("intfloat/multilingual-e5-base", device=device)

    @property
    def name(self) -> str:
        return self._name

    @property
    def dim(self) -> int:
        return self._dim

    def encode(
        self,
        texts: list[str],
        batch_size: int = 32,
        prefix: str = "passage: ",
    ) -> np.ndarray:
        prefixed = [f"{prefix}{t}" for t in texts]
        embeddings = self.model.encode(
            prefixed,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 100,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def encode_queries(self, queries: list[str], batch_size: int = 32) -> np.ndarray:
        return self.encode(queries, batch_size=batch_size, prefix="query: ")
