"""Context assembly under a token budget, with numbered citation markers."""

from __future__ import annotations

import re
from dataclasses import dataclass

from kinolog.retrieval import SearchResult

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
        selected_chunks.append(
            RetrievedChunkContext(
                item_id=r.item_id,
                title=r.title,
                year=r.year,
                chunk_id=r.chunk_id,
                text=text_snippet,
                score=r.score,
                citation_id=len(selected_chunks) + 1,
            )
        )

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
