"""Pull display facts (genres, overview) out of TMDB document text."""

from __future__ import annotations

import re

from src.core.db import Database


def parse_tmdb_text(text: str) -> dict:
    """Extract genres and the overview paragraph from text built by the TMDB enricher."""
    genres: list[str] = []
    m = re.search(r"^Genres:\s*(.+)$", text or "", re.MULTILINE)
    if m:
        genres = [g.strip() for g in m.group(1).split(",") if g.strip()]
    overview = ""
    blocks = [b.strip() for b in (text or "").split("\n\n") if b.strip()]
    if len(blocks) > 1:
        overview = blocks[-1]
    return {"genres": genres, "overview": overview}


def item_facts(db: Database, item_ids: list[int]) -> dict[int, dict]:
    """Batch genres/overview for items (English TMDB document preferred)."""
    out: dict[int, dict] = {i: {"genres": [], "overview": ""} for i in item_ids}
    if not item_ids:
        return out
    ph = ",".join("?" for _ in item_ids)
    rows = db.execute(
        f"""SELECT item_id, text FROM documents
            WHERE source = 'tmdb' AND item_id IN ({ph})
            ORDER BY (lang = 'en') ASC""",  # en last so it overwrites other languages
        tuple(item_ids),
    ).fetchall()
    for r in rows:
        facts = parse_tmdb_text(r["text"])
        if facts["genres"] or facts["overview"]:
            out[r["item_id"]] = facts
    return out
