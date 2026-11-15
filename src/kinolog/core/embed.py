"""Embedding model wrappers with batching."""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

from kinolog.config import DEFAULT_STRATEGY
from kinolog.store import Database

logger = logging.getLogger(__name__)


class EmbeddingModel(Protocol):
    """Protocol for embedding models."""

    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def encode(self, texts: list[str], batch_size: int = 32) -> np.ndarray: ...


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


def embed_chunks(
    db: Database,
    model: EmbeddingModel,
    strategy: str = DEFAULT_STRATEGY,
    batch_size: int = 64,
) -> dict:
    """
    Embed all chunks for a given strategy and store in the model's vec table.

    Returns stats about what was embedded.
    """
    # Ensure vec table exists
    db.try_create_vec_table(model.name, model.dim)

    vec_table = f"vec_{model.name}"

    # Get chunks that need embedding
    chunks = db.execute(
        """SELECT c.id, c.text FROM chunks c
           WHERE c.strategy = ?
           AND c.id NOT IN (SELECT chunk_id FROM {table})""".format(table=vec_table),
        (strategy,),
    ).fetchall()

    if not chunks:
        logger.info("No new chunks to embed for strategy '%s' / model '%s'", strategy, model.name)
        return {"total": 0, "embedded": 0}

    logger.info("Embedding %d chunks with %s...", len(chunks), model.name)

    chunk_ids = [c["id"] for c in chunks]
    chunk_texts = [c["text"] for c in chunks]

    # Batch encode
    all_embeddings = model.encode(chunk_texts, batch_size=batch_size)

    # Store in vec table
    for i, (chunk_id, embedding) in enumerate(zip(chunk_ids, all_embeddings)):
        db.execute(
            f"INSERT OR REPLACE INTO {vec_table} (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, embedding.tobytes()),
        )
        if (i + 1) % 500 == 0:
            db.conn.commit()
            logger.info("Stored %d/%d embeddings", i + 1, len(chunk_ids))

    db.conn.commit()
    logger.info("Embedded %d chunks", len(chunk_ids))
    return {"total": len(chunks), "embedded": len(chunk_ids)}
