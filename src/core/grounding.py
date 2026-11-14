"""Grounding: context assembly under a token budget, citation markers, and answer checks.

Shared by the chat agent and the Concierge so that "is this answer supported by what we
retrieved?" has one definition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.db import Database
from src.core.search import SearchResult

CITATION_RE = re.compile(r"\[\^(\d+)\]")


@dataclass
class RetrievedChunkContext:
    item_id: int
    title: str
    year: int | None
    chunk_id: int | None
    text: str
    score: float
    citation_id: int


@dataclass
class AssembledContext:
    chunks: list[RetrievedChunkContext]
    total_tokens: int
    context_text: str
    referenced_item_ids: set[int]


def assemble_context(
    results: list[SearchResult],
    token_budget: int = 1500,
) -> AssembledContext:
    """
    Assemble context from search results under a token budget.
    Deduplicates and formats citations as [^citation_id: Title (Year)].
    """
    selected_chunks: list[RetrievedChunkContext] = []
    total_tokens = 0
    ref_ids: set[int] = set()

    for r in results:
        # Estimate tokens (~3 chars/token)
        text_snippet = r.chunk_text.strip()
        tokens = max(1, len(text_snippet) // 3)

        if total_tokens + tokens > token_budget and selected_chunks:
            break

        total_tokens += tokens
        ref_ids.add(r.item_id)
        selected_chunks.append(RetrievedChunkContext(
            item_id=r.item_id,
            title=r.title,
            year=r.year,
            chunk_id=r.chunk_id,
            text=text_snippet,
            score=r.score,
            citation_id=len(selected_chunks) + 1,
        ))

    # Build prompt context text
    lines = ["=== RETRIEVED CONTEXT ==="]
    for c in selected_chunks:
        year_str = f" ({c.year})" if c.year else ""
        lines.append(f"\nSource [^{c.citation_id}]: {c.title}{year_str}")
        lines.append(f"{c.text}")
    lines.append("\n=========================")

    return AssembledContext(
        chunks=selected_chunks,
        total_tokens=total_tokens,
        context_text="\n".join(lines),
        referenced_item_ids=ref_ids,
    )


def groundedness(answer_items: list[int], context_items: set[int]) -> float:
    """Fraction of items mentioned in the answer that appear in the context."""
    if not answer_items:
        return 1.0  # vacuously true
    grounded = len(set(answer_items) & context_items)
    return grounded / len(answer_items)


def check_grounding(
    db: Database,
    answer: str,
    assembled: AssembledContext,
    mention_scope: set[int] | None = None,
) -> dict:
    """Check an answer against the context it was written from.

    Two checks: every item whose title the answer mentions must be in the context
    (``mention_scope`` limits which items' titles are looked for; None means every item in
    the DB), and every ``[^n]`` marker must refer to an assembled source.
    """
    if mention_scope is None:
        candidates = db.get_items()
    else:
        candidates = [it for it in (db.get_item(i) for i in mention_scope) if it]
    mentioned = [
        it["id"] for it in candidates
        if re.search(r"\b" + re.escape(it["title"]) + r"\b", answer, re.IGNORECASE)
    ]
    valid = {c.citation_id for c in assembled.chunks}
    invalid = sorted({int(n) for n in CITATION_RE.findall(answer) if int(n) not in valid})
    score = groundedness(mentioned, assembled.referenced_item_ids)
    return {
        "mentioned_item_ids": mentioned,
        "groundedness": score,
        "is_fully_grounded": score == 1.0,
        "invalid_citations": invalid,
        "citations_valid": not invalid,
    }
