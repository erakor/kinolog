"""Embed stored chunks with a model and write them to its vec table."""

from __future__ import annotations

import logging

from kinolog.config import DEFAULT_STRATEGY
from kinolog.index.embedding.base import EmbeddingModel
from kinolog.store import Database

logger = logging.getLogger(__name__)


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
        db.upsert_embedding(model.name, chunk_id, embedding.tobytes(), commit=False)
        if (i + 1) % 500 == 0:
            db.conn.commit()
            logger.info("Stored %d/%d embeddings", i + 1, len(chunk_ids))

    db.conn.commit()
    logger.info("Embedded %d chunks", len(chunk_ids))
    return {"total": len(chunks), "embedded": len(chunk_ids)}
