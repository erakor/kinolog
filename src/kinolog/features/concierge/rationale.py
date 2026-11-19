"""Rationale building: template text and structured facts from cited chunks."""

from __future__ import annotations

import re

from kinolog.features.docfacts import parse_tmdb_text

# --- picking ----------------------------------------------------------------------------

RATIONALE_TOKEN_BUDGET = 600


def _snippet(text: str, limit: int = 220) -> str:
    body = parse_tmdb_text(text)["overview"] or text
    body = re.sub(r"\s+", " ", body).strip()
    if len(body) <= limit:
        return body
    cut = body[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def _template_text(card: dict, filters: dict, deltas: list, hearts: dict, chunks: list) -> str:
    """Deterministic rationale built only from structured facts and cited chunk snippets."""
    parts: list[str] = []
    rt, cap = card.get("runtime_min"), filters.get("runtime_max")
    if rt and cap:
        parts.append(f"At {rt} minutes it fits your {cap}-minute window.")
    elif rt:
        parts.append(f"It runs {rt} minutes.")
    if card["directors"]:
        parts.append("Directed by " + ", ".join(d["name"] for d in card["directors"]) + ".")
    for c in chunks[:2]:
        snip = _snippet(c.text)
        if snip:
            parts.append(f"{snip} [^{c.citation_id}]")
    if deltas:
        d = deltas[0]
        parts.append(
            f"Watching it moves your {d.name} collection from {d.before_pct:.0f}% "
            f"to {d.after_pct:.0f}%."
        )
    for name, n in hearts.items():
        if n:
            parts.append(f"You hearted {n} other film{'s' if n != 1 else ''} by {name}.")
            break
    return " ".join(parts)


def _facts(card: dict, deltas: list, hearts: dict) -> list[dict]:
    facts = []
    if card.get("runtime_min"):
        facts.append(
            {"label": "Runtime", "value": f"{card['runtime_min']} min", "from": "items.runtime_min"}
        )
    if card["directors"]:
        facts.append(
            {
                "label": "Director",
                "value": ", ".join(d["name"] for d in card["directors"]),
                "from": "credits",
            }
        )
    for d in deltas[:1]:
        facts.append(
            {
                "label": "Completion",
                "value": f"{d.name}: {d.before_pct:.0f}% → {d.after_pct:.0f}%",
                "from": "collections",
            }
        )
    for name, n in hearts.items():
        if n:
            facts.append(
                {
                    "label": "Hearted by director",
                    "value": f"{n} × {name}",
                    "from": "user_status.liked",
                }
            )
            break
    return facts
