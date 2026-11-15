"""Load an SRT file as a document and store its scene-level chunks."""

from __future__ import annotations

import logging
from pathlib import Path

from kinolog.sources.subtitles.parse import (
    chunk_subtitles_by_gap,
    chunk_subtitles_by_window,
    ms_to_time,
    parse_srt,
)
from kinolog.store import Database

logger = logging.getLogger(__name__)


def load_and_chunk_subtitle_file(
    db: Database,
    item_id: int,
    srt_path: str | Path,
    lang: str = "fr",
    strategy: str = "sub_gap",
) -> list[int]:
    """
    Load an SRT file, store as a document, and chunk with subtitle timestamps into chunks table.
    """
    path = Path(srt_path)
    if not path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {path}")

    content = path.read_text(encoding="utf-8", errors="replace")
    entries = parse_srt(content)
    if not entries:
        return []

    full_text = "\n".join(f"[{ms_to_time(e.start_ms)}] {e.text}" for e in entries)
    doc_id = db.upsert_document(item_id, source="subtitle", lang=lang, text=full_text)

    if strategy == "sub_gap":
        sub_chunks = chunk_subtitles_by_gap(entries)
    else:
        sub_chunks = chunk_subtitles_by_window(entries)

    chunk_ids = []
    for c in sub_chunks:
        cid = db.upsert_chunk(
            item_id=item_id,
            document_id=doc_id,
            strategy=strategy,
            ord=c.ord,
            text=c.text,
            section_name=c.section_name,
            lang=lang,
            token_count=c.token_count,
            start_ms=c.start_ms,
            end_ms=c.end_ms,
        )
        chunk_ids.append(cid)

    logger.info("Loaded and chunked subtitle for item %d (%d chunks, strategy '%s')",
                item_id, len(chunk_ids), strategy)
    return chunk_ids
