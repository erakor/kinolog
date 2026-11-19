"""Run a registered strategy over stored documents and write the chunks."""

from __future__ import annotations

import logging

from kinolog.config import DEFAULT_STRATEGY
from kinolog.index.chunking.base import STRATEGIES
from kinolog.store import Database

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~3 for multilingual."""
    return max(1, len(text) // 3)


def chunk_document(
    db: Database,
    document_id: int,
    strategy: str = DEFAULT_STRATEGY,
) -> list[int]:
    """
    Chunk a document with the given strategy and store in DB.

    Returns list of chunk IDs.
    """
    doc = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    chunk_fn = STRATEGIES.get(strategy)
    if not chunk_fn:
        raise ValueError(f"Unknown strategy: {strategy}. Available: {list(STRATEGIES.keys())}")

    # Check if already chunked with this strategy (idempotent)
    existing = db.execute(
        "SELECT id FROM chunks WHERE document_id = ? AND strategy = ?",
        (document_id, strategy),
    ).fetchall()
    if existing:
        first_chunk = db.execute(
            "SELECT content_hash FROM chunks WHERE document_id = ? AND strategy = ? LIMIT 1",
            (document_id, strategy),
        ).fetchone()
        if first_chunk and first_chunk["content_hash"]:
            # Check if source text changed
            pass  # Re-chunk below if needed; for now, skip
        return [r["id"] for r in existing]

    chunks = chunk_fn(doc["text"])
    chunk_ids = []

    for chunk in chunks:
        chunk_id = db.upsert_chunk(
            item_id=doc["item_id"],
            document_id=document_id,
            strategy=strategy,
            ord=chunk.ord,
            text=chunk.text,
            section_name=chunk.section_name,
            lang=doc["lang"],
            token_count=chunk.token_count,
            start_ms=chunk.start_ms,
            end_ms=chunk.end_ms,
        )
        chunk_ids.append(chunk_id)

    logger.debug(
        "Chunked document %d with strategy '%s': %d chunks",
        document_id,
        strategy,
        len(chunk_ids),
    )
    return chunk_ids


def chunk_all_documents(
    db: Database,
    strategy: str = DEFAULT_STRATEGY,
    item_type: str | None = None,
) -> dict:
    """Chunk all documents. Returns stats."""
    sql = "SELECT d.id FROM documents d"
    params: list = []
    if item_type:
        sql += " JOIN items i ON d.item_id = i.id WHERE i.item_type = ?"
        params.append(item_type)

    docs = db.execute(sql, tuple(params)).fetchall()
    stats = {"total": len(docs), "chunks_created": 0}

    for doc in docs:
        chunk_ids = chunk_document(db, doc["id"], strategy=strategy)
        stats["chunks_created"] += len(chunk_ids)

    logger.info(
        "Chunked %d documents with '%s': %d chunks total",
        stats["total"],
        strategy,
        stats["chunks_created"],
    )
    return stats
