"""Chunking strategies for documents."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from kinolog.core.db import Database, content_hash

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    text: str
    ord: int
    section_name: str | None = None
    token_count: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~3 for multilingual."""
    return max(1, len(text) // 3)


def chunk_fixed_window(
    text: str,
    window_tokens: int = 256,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Fixed-size token windows with overlap."""
    # Use character approximation (3 chars/token for multilingual)
    chars_per_token = 3
    window_chars = window_tokens * chars_per_token
    overlap_chars = overlap_tokens * chars_per_token

    chunks = []
    start = 0
    ord_idx = 0

    while start < len(text):
        end = start + window_chars
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(Chunk(
                text=chunk_text,
                ord=ord_idx,
                token_count=_estimate_tokens(chunk_text),
            ))
            ord_idx += 1
        start = end - overlap_chars
        if start >= len(text):
            break

    return chunks


def chunk_whole_document(text: str) -> list[Chunk]:
    """One chunk per document — baseline strategy."""
    return [Chunk(text=text.strip(), ord=0, token_count=_estimate_tokens(text))]


def chunk_by_section(
    text: str,
    prepend_title: bool = True,
) -> list[Chunk]:
    """
    Section-aware chunking.

    Splits on lines that look like section headers (lines ending with ':' or
    lines that are short and followed by longer content).
    """
    lines = text.split("\n")
    if not lines:
        return []

    # Extract title (first non-empty line)
    title_line = ""
    for line in lines:
        if line.strip():
            title_line = line.strip()
            break

    # Find sections: lines that look like "Category:" or short header lines
    sections = []
    current_name = "header"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Detect section headers
        if (
            stripped.endswith(":")
            and len(stripped) < 60
            and len(stripped) > 2
        ):
            if current_lines:
                sections.append((current_name, "\n".join(current_lines).strip()))
            current_name = stripped.rstrip(":")
            current_lines = []
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_lines:
        sections.append((current_name, "\n".join(current_lines).strip()))

    # Build chunks
    chunks = []
    for i, (section_name, section_text) in enumerate(sections):
        if not section_text.strip():
            continue
        text_with_prefix = section_text
        if prepend_title and section_name != "header":
            text_with_prefix = f"{title_line}\n[{section_name}]\n{section_text}"
        chunks.append(Chunk(
            text=text_with_prefix,
            ord=i,
            section_name=section_name,
            token_count=_estimate_tokens(text_with_prefix),
        ))

    return chunks


# Strategy registry
STRATEGIES = {
    "whole": chunk_whole_document,
    "fixed_256_50": lambda text: chunk_fixed_window(text, 256, 50),
    "fixed_512_100": lambda text: chunk_fixed_window(text, 512, 100),
    "section": lambda text: chunk_by_section(text, prepend_title=True),
    "section_no_prefix": lambda text: chunk_by_section(text, prepend_title=False),
}


def chunk_document(
    db: Database,
    document_id: int,
    strategy: str = "whole",
) -> list[int]:
    """
    Chunk a document with the given strategy and store in DB.

    Returns list of chunk IDs.
    """
    doc = db.execute(
        "SELECT * FROM documents WHERE id = ?", (document_id,)
    ).fetchone()
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
        c_hash = content_hash(doc["text"])
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
        document_id, strategy, len(chunk_ids),
    )
    return chunk_ids


def chunk_all_documents(
    db: Database,
    strategy: str = "whole",
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

    logger.info("Chunked %d documents with '%s': %d chunks total",
                stats["total"], strategy, stats["chunks_created"])
    return stats
