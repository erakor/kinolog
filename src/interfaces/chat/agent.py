"""Chat agent loop: context assembly under a token budget and grounded, cited answers."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from src.core.db import Database
from src.core.search import SearchFilters, SearchResult, search
from src.eval.metrics import groundedness

logger = logging.getLogger(__name__)

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

    for idx, r in enumerate(results):
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


class KinologChatAgent:
    """Chat agent that retrieves context and generates grounded answers with citations."""

    def __init__(self, db: Database, model_embed: Any = None):
        self.db = db
        self.model_embed = model_embed

    def answer_query(
        self,
        question: str,
        token_budget: int = 1500,
        search_mode: str = "bm25",
        generator_fn: Callable[[str, str], str] | None = None,
        *,
        filters: SearchFilters | None = None,
        results: list[SearchResult] | None = None,
        limit: int = 10,
        mention_scope: set[int] | None = None,
    ) -> dict[str, Any]:
        """
        1. Retrieve top chunks via search (skipped when ``results`` is given)
        2. Assemble context under token budget
        3. Generate answer grounded in context
        4. Validate groundedness of mentioned films and the validity of [^n] citations

        ``mention_scope`` limits the titles checked for mentions to those item ids (a
        candidate set); None checks every item in the DB, as before.
        """
        if results is None:
            results = search(
                self.db,
                question,
                model=self.model_embed,
                mode=search_mode,
                limit=limit,
                filters=filters,
                dedupe_items=False,
            )

        assembled = assemble_context(results, token_budget=token_budget)

        # Default generator synthesis if no LLM generator provided
        if generator_fn is None:
            # Deterministic synthesis for evaluation and local use
            if not assembled.chunks:
                answer = (
                    "I could not find any matching films or books in your index for that query."
                )
            else:
                items_summary = []
                for c in assembled.chunks[:5]:
                    year_str = f" ({c.year})" if c.year else ""
                    items_summary.append(
                        f"- **{c.title}**{year_str} [^{c.citation_id}]: {c.text[:140]}..."
                    )
                answer = (
                    "Based on your index, here are relevant items:\n\n"
                    + "\n".join(items_summary)
                )
        else:
            answer = generator_fn(question, assembled.context_text)

        # Extract mentioned item titles to check grounding
        mentioned_item_ids = []
        if mention_scope is None:
            candidates = self.db.get_items()
        else:
            candidates = [it for it in (self.db.get_item(i) for i in mention_scope) if it]
        for item in candidates:
            pattern = r"\b" + re.escape(item["title"]) + r"\b"
            if re.search(pattern, answer, re.IGNORECASE):
                mentioned_item_ids.append(item["id"])

        valid_ids = {c.citation_id for c in assembled.chunks}
        invalid_citations = sorted(
            {int(n) for n in CITATION_RE.findall(answer) if int(n) not in valid_ids}
        )

        grounded_score = groundedness(mentioned_item_ids, assembled.referenced_item_ids)

        return {
            "question": question,
            "answer": answer,
            "context": assembled.context_text,
            "citations": [
                {
                    "citation_id": c.citation_id, "item_id": c.item_id,
                    "title": c.title, "year": c.year,
                }
                for c in assembled.chunks
            ],
            "mentioned_item_ids": mentioned_item_ids,
            "context_item_ids": list(assembled.referenced_item_ids),
            "groundedness": grounded_score,
            "is_fully_grounded": grounded_score == 1.0,
            "invalid_citations": invalid_citations,
            "citations_valid": not invalid_citations,
        }
