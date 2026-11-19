"""Chat agent loop: context assembly under a token budget and grounded, cited answers."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from kinolog.rag.context import AssembledContext, RetrievedChunkContext, assemble_context
from kinolog.rag.grounding import check_grounding
from kinolog.retrieval import SearchFilters, SearchResult, search
from kinolog.store import Database

logger = logging.getLogger(__name__)

__all__ = ["AssembledContext", "KinologChatAgent", "RetrievedChunkContext", "assemble_context"]


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
                answer = "Based on your index, here are relevant items:\n\n" + "\n".join(
                    items_summary
                )
        else:
            answer = generator_fn(question, assembled.context_text)

        check = check_grounding(self.db, answer, assembled, mention_scope)

        return {
            "question": question,
            "answer": answer,
            "context": assembled.context_text,
            "citations": [
                {
                    "citation_id": c.citation_id,
                    "item_id": c.item_id,
                    "title": c.title,
                    "year": c.year,
                }
                for c in assembled.chunks
            ],
            "context_item_ids": list(assembled.referenced_item_ids),
            **check,
        }
