"""Answer checks: groundedness and mention scope.

Shared by the chat agent and the Concierge so that "is this answer supported by what we
retrieved?" has one definition."""

from __future__ import annotations

import re

from kinolog.rag.context import CITATION_RE, AssembledContext
from kinolog.store import Database, chunked


def groundedness(answer_items: list[int], context_items: set[int]) -> float:
    """Fraction of items mentioned in the answer that appear in the context."""
    if not answer_items:
        return 1.0  # vacuously true
    grounded = len(set(answer_items) & context_items)
    return grounded / len(answer_items)


class MentionScope:
    """Film titles to look for in answers, compiled once and reusable across checks.

    ``item_ids=None`` means every item in the DB. Titles are matched case-insensitively on
    word boundaries with one alternation (longest title first).
    """

    def __init__(self, db: Database, item_ids: set[int] | None = None):
        if item_ids is None:
            rows = db.execute("SELECT id, title FROM items").fetchall()
        else:
            rows = []
            for part in chunked(sorted(item_ids)):
                ph = ",".join("?" for _ in part)
                rows += db.execute(
                    f"SELECT id, title FROM items WHERE id IN ({ph})", tuple(part)
                ).fetchall()
        self._ids_by_title: dict[str, list[int]] = {}
        for r in rows:
            if r["title"]:
                self._ids_by_title.setdefault(r["title"].lower(), []).append(r["id"])
        titles = sorted(self._ids_by_title, key=len, reverse=True)
        self._pattern = (
            re.compile(r"\b(?:" + "|".join(re.escape(t) for t in titles) + r")\b", re.IGNORECASE)
            if titles else None
        )

    def mentioned(self, answer: str) -> list[int]:
        if self._pattern is None:
            return []
        found = {m.group(0).lower() for m in self._pattern.finditer(answer)}
        return [i for t in found for i in self._ids_by_title.get(t, [])]


def check_grounding(
    db: Database,
    answer: str,
    assembled: AssembledContext,
    mention_scope: set[int] | MentionScope | None = None,
) -> dict:
    """Check an answer against the context it was written from.

    Two checks: every item whose title the answer mentions must be in the context
    (``mention_scope`` limits which items' titles are looked for; None means every item in
    the DB), and every ``[^n]`` marker must refer to an assembled source.
    """
    scope = mention_scope if isinstance(mention_scope, MentionScope) else MentionScope(
        db, mention_scope
    )
    mentioned = scope.mentioned(answer)
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
