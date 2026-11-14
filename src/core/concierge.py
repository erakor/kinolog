"""Concierge: deterministic constraint parsing, filtered retrieval and grounded picks.

The parser is regex + small lexicons (no LLM) so it is testable and works offline.
Matched constraint phrases are removed from the residual query, because the BM25 index
contains literal text like "Runtime: 90 minutes" that such phrases would otherwise match.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from src.core import collections as coll
from src.core.db import Database
from src.core.docfacts import item_facts, parse_tmdb_text
from src.core.search import SearchFilters, SearchResult, search

# --- lexicons ---------------------------------------------------------------------------

_MAX_Q = (
    r"under|below|less\s+than|fewer\s+than|at\s+most|no\s+more\s+than|not\s+more\s+than|up\s+to|"
    r"within|in\s+less\s+than|shorter\s+than|max(?:imum)?(?:\s+of)?|<=|<|≤"
)
_MIN_Q = (
    r"over|above|more\s+than|at\s+least|no\s+less\s+than|longer\s+than|min(?:imum)?(?:\s+of)?|"
    r">=|>|≥"
)
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4}

DURATION_RE = re.compile(
    rf"""(?:(?P<q>{_MAX_Q}|{_MIN_Q})\s*)?
    (?P<d>
        (?P<h1>\d+)\s*h(?:ours?|rs?)?\s*(?:and\s+)?(?P<m1>\d{{1,2}})\s*(?:minutes?|mins?|min|m)?
      | (?P<hd>\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h)
      | (?P<hw>one|two|three|four)\s+hours?(?P<half>\s+and\s+a\s+half)?
      | (?P<hh>(?:an?\s+)?hour\s+and\s+a\s+half|half\s+an?\s+hour|half\s+hour|an?\s+hour)
      | (?P<mn>\d+)\s*(?:minutes?|mins?|min)
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

_DECADE_WORDS = {
    "twenties": 1920, "thirties": 1930, "forties": 1940, "fifties": 1950, "sixties": 1960,
    "seventies": 1970, "eighties": 1980, "nineties": 1990,
}
_DECADE_LEAD = r"(?:(?:from|in|of|during)\s+(?:the\s+)?|the\s+)?"
DECADE_RE = re.compile(
    rf"""{_DECADE_LEAD}(?:
        (?P<d4>(?:18|19|20)\d0)['’]?s
      | ['’]?(?P<d2>\d0)['’]?s
      | (?P<dw>{"|".join(_DECADE_WORDS)})
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

YEAR = r"(?:18|19|20)\d\d"
BETWEEN_RE = re.compile(
    rf"\b(?:between\s+(?P<a>{YEAR})\s+and\s+(?P<b>{YEAR})|(?P<a2>{YEAR})\s*(?:-|–|to)\s*(?P<b2>{YEAR}))\b",
    re.IGNORECASE,
)
YEAR_BOUND_RE = re.compile(
    rf"\b(?P<q>before|prior\s+to|pre-?|until|up\s+to|no\s+later\s+than|after|since|post-?|"
    rf"later\s+than|from|in)\s*(?P<y>{YEAR})\b(?!['\u2019]?s\b)",
    re.IGNORECASE,
)

NOT_SEEN_RE = re.compile(
    r"\b(?:(?:i\s+)?(?:haven'?t|have\s+not|hasn'?t|never)\s+(?:yet\s+)?(?:seen|watched)(?:\s+yet)?"
    r"|not\s+(?:yet\s+)?seen|unseen|new\s+to\s+me)\b",
    re.IGNORECASE,
)
SEEN_RE = re.compile(
    r"\b(?:already\s+seen|(?:i(?:'ve|\s+have)\s+)?seen\s+before|re-?watch(?:ing)?)\b", re.IGNORECASE
)
WATCHLIST_RE = re.compile(
    r"\b(?:(?:from|on|in|off)\s+)?my\s+watch\s*list\b", re.IGNORECASE
)
BOOK_RE = re.compile(r"\b(?:books?|novels?)\b", re.IGNORECASE)
FILM_RE = re.compile(r"\b(?:films?|movies?|flicks?|pictures?)\b", re.IGNORECASE)
SHORT_RE = re.compile(r"\b(?:something|a|an|really|very)?\s*(?:short|brief|quick)\b", re.IGNORECASE)
COMPLETION_RE = re.compile(
    r"\b(?:finish|complete|completing|completion|completist)\b", re.IGNORECASE
)
COLLECTION_WORD_RE = re.compile(r"\b(?:director|directors|collection|filmography)\b", re.IGNORECASE)
LANG_RE = re.compile(
    r"\b(italian|french|japanese|korean|german|spanish|swedish|russian|chinese|"
    r"hindi|portuguese|polish|danish|iranian|mexican|brazilian)\b",
    re.IGNORECASE,
)

SHORT_RUNTIME_MAX = 100

STOPWORDS = {
    "i", "i'm", "im", "i've", "ive", "have", "has", "had", "give", "me", "a", "an", "the", "some",
    "something", "anything", "to", "watch", "watching", "tonight", "today", "now", "please",
    "want", "wanna", "would", "could", "should", "what", "which", "can", "you", "suggest",
    "recommend", "find", "show", "pick", "need", "for", "of", "in", "on", "that", "is", "it",
    "my", "tonights", "just", "got", "with", "about", "and", "or", "but", "so", "from", "up",
    "yet", "time", "free", "got", "only", "really", "very", "any", "be", "something's",
}


@dataclass
class Chip:
    kind: str
    label: str
    source_span: tuple[int, int]


@dataclass
class ParsedQuery:
    residual_query: str
    filters: dict = field(default_factory=dict)
    chips: list[Chip] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)
    intent: str | None = None  # "completion" when the user asks to finish a filmography

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chips"] = [
            {"kind": c.kind, "label": c.label, "source_span": list(c.source_span)}
            for c in self.chips
        ]
        return d


# --- parsing ----------------------------------------------------------------------------


class _Spans:
    def __init__(self, text: str):
        self.text = text
        self.used = [False] * len(text)

    def free(self, start: int, end: int) -> bool:
        return not any(self.used[start:end])

    def take(self, start: int, end: int) -> None:
        for i in range(start, end):
            self.used[i] = True

    def residual(self) -> str:
        return "".join(" " if u else c for c, u in zip(self.text, self.used, strict=True))


def _duration_minutes(m: re.Match) -> int:
    if m.group("h1"):
        return int(m.group("h1")) * 60 + int(m.group("m1"))
    if m.group("hd"):
        return round(float(m.group("hd")) * 60)
    if m.group("hw"):
        base = _WORD_NUM[m.group("hw").lower()] * 60
        return base + (30 if m.group("half") else 0)
    if m.group("hh"):
        t = re.sub(r"\s+", " ", m.group("hh").lower())
        return 90 if "half" in t and "hour and" in t else 30 if t.startswith("half") else 60
    return int(m.group("mn"))


def _fmt_minutes(n: int) -> str:
    return f"{n} min"


def parse_constraints(text: str) -> ParsedQuery:
    spans = _Spans(text)
    filters: dict = {}
    chips: list[Chip] = []
    unparsed: list[str] = []

    def chip(kind: str, label: str, m: re.Match) -> None:
        chips.append(Chip(kind, label, (m.start(), m.end())))

    # runtime
    for m in DURATION_RE.finditer(text):
        if not spans.free(m.start(), m.end()):
            continue
        minutes = _duration_minutes(m)
        q = (m.group("q") or "").lower()
        if q and re.fullmatch(_MIN_Q, q, re.IGNORECASE) and "runtime_min" not in filters:
            filters["runtime_min"] = minutes
            chip("runtime_min", f"≥ {_fmt_minutes(minutes)}", m)
        elif "runtime_max" not in filters:
            filters["runtime_max"] = minutes
            chip("runtime_max", f"≤ {_fmt_minutes(minutes)}", m)
        else:
            continue
        spans.take(m.start(), m.end())

    # explicit year ranges, then bounds
    for m in BETWEEN_RE.finditer(text):
        if not spans.free(m.start(), m.end()):
            continue
        a, b = int(m.group("a") or m.group("a2")), int(m.group("b") or m.group("b2"))
        lo, hi = min(a, b), max(a, b)
        filters["year_min"], filters["year_max"] = lo, hi
        chip("years", f"{lo}–{hi}", m)
        spans.take(m.start(), m.end())
    for m in YEAR_BOUND_RE.finditer(text):
        if not spans.free(m.start(), m.end()):
            continue
        q, y = re.sub(r"[\s-]+", " ", m.group("q").lower()).strip(), int(m.group("y"))
        if q in ("before", "prior to", "pre"):
            filters.setdefault("year_max", y - 1)
            chip("year_max", f"before {y}", m)
        elif q in ("until", "up to", "no later than"):
            filters.setdefault("year_max", y)
            chip("year_max", f"until {y}", m)
        elif q in ("after", "post", "later than"):
            filters.setdefault("year_min", y + 1)
            chip("year_min", f"after {y}", m)
        elif q in ("since", "from"):
            filters.setdefault("year_min", y)
            chip("year_min", f"since {y}", m)
        else:  # "in 1962"
            filters.setdefault("year_min", y)
            filters.setdefault("year_max", y)
            chip("years", str(y), m)
        spans.take(m.start(), m.end())

    # decade
    for m in DECADE_RE.finditer(text):
        if not spans.free(m.start(), m.end()) or "decade" in filters:
            continue
        if m.group("d4"):
            decade = int(m.group("d4"))
        elif m.group("d2"):
            nn = int(m.group("d2"))
            decade = 2010 if nn == 10 else 1900 + nn
        else:
            decade = _DECADE_WORDS[m.group("dw").lower()]
        filters["decade"] = decade
        chip("decade", f"{decade}s", m)
        spans.take(m.start(), m.end())

    # watch status / scope
    for m in NOT_SEEN_RE.finditer(text):
        if spans.free(m.start(), m.end()) and "seen" not in filters:
            filters["seen"] = False
            chip("seen", "not seen", m)
            spans.take(m.start(), m.end())
    for m in SEEN_RE.finditer(text):
        if spans.free(m.start(), m.end()) and "seen" not in filters:
            filters["seen"] = True
            chip("seen", "already seen", m)
            spans.take(m.start(), m.end())
    for m in WATCHLIST_RE.finditer(text):
        if spans.free(m.start(), m.end()):
            filters["on_watchlist"] = True
            chip("on_watchlist", "from your Watch List", m)
            spans.take(m.start(), m.end())

    # "short" means a short runtime (only if no explicit runtime was given)
    if "runtime_max" not in filters:
        for m in SHORT_RE.finditer(text):
            if spans.free(m.start(), m.end()):
                filters["runtime_max"] = SHORT_RUNTIME_MAX
                chip("runtime_max", f"≤ {_fmt_minutes(SHORT_RUNTIME_MAX)}", m)
                spans.take(m.start(), m.end())
                break

    # item type
    for m in BOOK_RE.finditer(text):
        if spans.free(m.start(), m.end()):
            filters["item_type"] = "book"
            chip("item_type", "book", m)
            spans.take(m.start(), m.end())
            break
    if "item_type" not in filters:
        for m in FILM_RE.finditer(text):
            if spans.free(m.start(), m.end()):
                filters["item_type"] = "film"
                spans.take(m.start(), m.end())  # filler word; no chip needed
                break

    # languages/countries: no structured column yet, so keep the word for retrieval
    for m in LANG_RE.finditer(text):
        if spans.free(m.start(), m.end()):
            unparsed.append(f"language: {m.group(1).lower()}")

    tokens = re.findall(r"[\w'’À-ſ-]+", spans.residual())
    residual = " ".join(t for t in tokens if t.lower().strip("'’") not in STOPWORDS)
    intent = None
    if COMPLETION_RE.search(text) and COLLECTION_WORD_RE.search(text):
        intent = "completion"
        chips.append(Chip("intent", "finish a filmography", (0, len(text))))
    return ParsedQuery(
        residual_query=residual, filters=filters, chips=chips, unparsed=unparsed, intent=intent
    )


def to_search_filters(
    parsed: ParsedQuery,
    scope: str = "unseen",
    exclude_ids: list[int] | None = None,
    item_ids: list[int] | None = None,
) -> SearchFilters:
    """Merge parsed constraints with the UI scope. Phrases in the query win over the scope.

    The v1 UI is films-only, so ``item_type`` is always ``film``.
    """
    f = parsed.filters
    seen = f.get("seen")
    on_watchlist = f.get("on_watchlist")
    if seen is None and on_watchlist is None:
        if scope == "unseen":
            seen = False
        elif scope == "watchlist":
            on_watchlist = True
    return SearchFilters(
        item_type="film",
        features_only=True,
        seen=seen,
        on_watchlist=on_watchlist,
        decade=f.get("decade"),
        year_min=f.get("year_min"),
        year_max=f.get("year_max"),
        runtime_min=f.get("runtime_min"),
        runtime_max=f.get("runtime_max"),
        exclude_ids=exclude_ids,
        item_ids=item_ids,
    )


# --- picking ----------------------------------------------------------------------------

RATIONALE_TOKEN_BUDGET = 600
CANDIDATE_LIMIT = 50


def _snippet(text: str, limit: int = 220) -> str:
    body = parse_tmdb_text(text)["overview"] or text
    body = re.sub(r"\s+", " ", body).strip()
    if len(body) <= limit:
        return body
    cut = body[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def _filter_only_candidates(
    db: Database, filters: SearchFilters, limit: int
) -> list[int]:
    """Candidate item ids from filters alone (no text query)."""
    item_cond, params = filters.to_sql_conditions()
    status_cond, sparams = filters.to_status_conditions()
    sql = "SELECT i.id FROM items i LEFT JOIN user_status us ON us.item_id = i.id"
    conds = [c for c in (item_cond, status_cond) if c]
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    rows = db.execute(sql + " LIMIT 2000", tuple(params + sparams)).fetchall()
    return [r["id"] for r in rows][:limit * 40]


def _count_unknown_runtime(db: Database, filters: SearchFilters) -> int:
    if filters.runtime_min is None and filters.runtime_max is None:
        return 0
    relaxed = SearchFilters(**{**filters.__dict__, "runtime_min": None, "runtime_max": None})
    item_cond, params = relaxed.to_sql_conditions()
    status_cond, sparams = relaxed.to_status_conditions()
    conds = [c for c in (item_cond, status_cond, "i.runtime_min IS NULL") if c]
    row = db.execute(
        "SELECT COUNT(*) AS n FROM items i LEFT JOIN user_status us ON us.item_id = i.id"
        " WHERE " + " AND ".join(conds),
        tuple(params + sparams),
    ).fetchone()
    return row["n"]


def _director_item_ids(db: Database, query: str) -> tuple[str | None, list[int]]:
    """If the query names a director in the index, return (name, their counted films)."""
    rows = db.execute(
        "SELECT DISTINCT p.id, p.name FROM people p JOIN credits c ON c.person_id = p.id"
        " WHERE c.role = 'Director'"
    ).fetchall()
    low = query.lower()
    best = None
    for r in rows:
        name = r["name"]
        if len(name) >= 4 and name.lower() in low and (best is None or len(name) > len(best[1])):
            best = (r["id"], name)
    if not best:
        return None, []
    ids = db.execute(
        f"""SELECT DISTINCT i.id FROM credits c JOIN items i ON i.id = c.item_id
            WHERE c.person_id = ? AND c.role = 'Director' AND {coll.COUNTED}""",
        (best[0],),
    ).fetchall()
    return best[1], [r["id"] for r in ids]


def _mention_scope(db: Database) -> set[int]:
    """Films whose titles are checked for mentions in a rationale.

    Every film in the index counts (so naming a film that is not in the cited context is
    caught), minus titles under 4 characters or that are plain stopwords ("M", "It", "Her"),
    which would match ordinary prose.
    """
    rows = db.execute("SELECT id, title FROM items WHERE item_type = 'film'").fetchall()
    return {
        r["id"] for r in rows
        if len(r["title"]) >= 4 and r["title"].lower() not in STOPWORDS
    }


def _gain(deltas: list[coll.CompletionDelta]) -> float:
    return max((d.after_pct - d.before_pct for d in deltas), default=0.0)


def _chunk_meta(db: Database, chunk_ids: list[int]) -> dict[int, dict]:
    ids = [c for c in chunk_ids if c is not None]
    if not ids:
        return {}
    ph = ",".join("?" for _ in ids)
    rows = db.execute(
        f"""SELECT c.id, c.section_name, d.source FROM chunks c
            JOIN documents d ON d.id = c.document_id WHERE c.id IN ({ph})""",
        tuple(ids),
    ).fetchall()
    return {r["id"]: {"section_name": r["section_name"], "source": r["source"]} for r in rows}


def _item_chunks(
    db: Database, item_id: int, residual: str, model: Any, mode: str
) -> list[SearchResult]:
    """Most relevant chunks of one item (query-scoped), else its leading chunks."""
    if residual:
        found = search(
            db, residual, model=model, mode=mode, limit=3,
            filters=SearchFilters(item_ids=[item_id]), dedupe_items=False,
        )
        if found:
            return found
    item = db.get_item(item_id) or {}
    rows = db.execute(
        "SELECT id, text FROM chunks WHERE item_id = ? ORDER BY (strategy = 'whole') DESC, ord"
        " LIMIT 2",
        (item_id,),
    ).fetchall()
    return [
        SearchResult(
            item_id=item_id, chunk_id=r["id"], score=0.0, title=item.get("title", ""),
            year=item.get("year"), chunk_text=r["text"], source="chunk",
        )
        for r in rows
    ]


def _hearts_by_director(db: Database, person_id: int, exclude_item: int) -> int:
    row = db.execute(
        """SELECT COUNT(DISTINCT c.item_id) AS n FROM credits c
           JOIN user_status us ON us.item_id = c.item_id
           WHERE c.person_id = ? AND c.role = 'Director' AND us.liked = 1 AND c.item_id != ?""",
        (person_id, exclude_item),
    ).fetchone()
    return row["n"]


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
        facts.append({"label": "Runtime", "value": f"{card['runtime_min']} min",
                      "from": "items.runtime_min"})
    if card["directors"]:
        facts.append({"label": "Director", "value": ", ".join(d["name"] for d in card["directors"]),
                      "from": "credits"})
    for d in deltas[:1]:
        facts.append({"label": "Completion",
                      "value": f"{d.name}: {d.before_pct:.0f}% → {d.after_pct:.0f}%",
                      "from": "collections"})
    for name, n in hearts.items():
        if n:
            facts.append({"label": "Hearted by director", "value": f"{n} × {name}",
                          "from": "user_status.liked"})
            break
    return facts


def pick(
    db: Database,
    query: str,
    *,
    model: Any = None,
    scope: str = "unseen",
    limit: int = 5,
    generator_fn: Callable[[str, str], str] | None = None,
    taste_fn: Callable[[list[int]], dict[int, float]] | None = None,
    w_taste: float = 0.0,
    w_comp: float = 0.0,
) -> dict:
    """Parse constraints, retrieve under SQL filters, optionally rerank, add grounded rationales.

    ``w_taste`` and ``w_comp`` default to 0 (pure retrieval order) until an eval justifies more.
    """
    from src.interfaces.chat.agent import KinologChatAgent, assemble_context

    parsed = parse_constraints(query)
    degraded: list[str] = []
    if parsed.filters.get("item_type") == "book":
        degraded.append("books_not_supported: this view recommends films only")

    director_name, director_ids = _director_item_ids(db, query)
    filters = to_search_filters(parsed, scope, item_ids=director_ids if director_name else None)
    if director_name:
        parsed.chips.append(Chip("director", director_name, (0, 0)))

    if model is not None and db.vec_available:
        mode = "rrf"
    else:
        mode = "bm25"
        degraded.append(
            "no_vector: sqlite-vec unavailable" if not db.vec_available
            else "no_model: embedding model not loaded"
        )

    residual = "" if (parsed.intent == "completion" or director_name) else parsed.residual_query
    ranked: list[tuple[int, float]]
    if residual:
        results = search(db, residual, model=model, mode=mode, limit=CANDIDATE_LIMIT,
                         filters=filters, dedupe_items=True)
        top = results[0].score if results and results[0].score else 1.0
        ranked = [(r.item_id, r.score / top) for r in results]
    else:
        cand = _filter_only_candidates(db, filters, limit)
        ranked = [(i, 0.0) for i in cand]

    cand_ids = [i for i, _ in ranked]
    deltas_all = coll.completion_deltas(db, cand_ids, with_remaining=False)
    taste: dict[int, float] = {}
    if w_taste > 0 and taste_fn and cand_ids:
        try:
            taste = taste_fn(cand_ids)
        except Exception:
            degraded.append("no_taste: taste ranking unavailable")

    on_list_ids = set(db.get_watchlist_ids())

    def key(entry: tuple[int, float]) -> tuple:
        item_id, base = entry
        gain = _gain(deltas_all.get(item_id, []))
        score = base + w_taste * taste.get(item_id, 0.0) + w_comp * gain / 100.0
        if residual:
            return (-score,)
        on_list = 1 if item_id in on_list_ids else 0
        if parsed.intent == "completion" or director_name:
            return (-gain, -on_list, -score)
        return (-on_list, -gain, -score)

    ranked.sort(key=key)
    top_ids = [i for i, _ in ranked[:limit]]
    cards = db.get_item_cards(top_ids)
    for item_id, f in item_facts(db, top_ids).items():
        cards[item_id]["genres"] = f["genres"]
    deltas = coll.completion_deltas(db, top_ids, with_remaining=True)
    mention_scope = _mention_scope(db)
    agent = KinologChatAgent(db, model_embed=model)

    picks = []
    for item_id in top_ids:
        card = cards[item_id]
        base = dict(ranked)[item_id]
        gain = _gain(deltas.get(item_id, []))
        score = base + w_taste * taste.get(item_id, 0.0) + w_comp * gain / 100.0
        chunks = _item_chunks(db, item_id, residual, model, mode)
        assembled = assemble_context(chunks, token_budget=RATIONALE_TOKEN_BUDGET)
        hearts = {
            d["name"]: _hearts_by_director(db, d["person_id"], item_id) for d in card["directors"]
        }
        facts = _facts(card, deltas.get(item_id, []), hearts)

        def template(_q: str, _ctx: str, card=card, item_id=item_id, assembled=assembled,
                     hearts=hearts) -> str:
            return _template_text(
                card, parsed.filters, deltas.get(item_id, []), hearts, assembled.chunks
            )

        generator = "template"
        out = agent.answer_query(
            query, results=chunks, generator_fn=template, mention_scope=mention_scope
        )
        if generator_fn is not None:
            facts_block = "\n".join(f"Fact: {f['label']}: {f['value']}" for f in facts)

            def llm(q: str, ctx: str, facts_block=facts_block) -> str:
                return generator_fn(q, ctx + "\n" + facts_block)

            try:
                llm_out = agent.answer_query(
                    query, results=chunks, generator_fn=llm, mention_scope=mention_scope
                )
                ok = (
                    llm_out["is_fully_grounded"] and llm_out["citations_valid"]
                    and (not assembled.chunks or "[^" in llm_out["answer"])
                )
            except Exception:
                ok = False
            if ok:
                out, generator = llm_out, "llm"
            elif "llm_ungrounded" not in degraded:
                degraded.append("llm_ungrounded: fell back to template rationale")
        elif "no_llm: template rationale" not in degraded:
            degraded.append("no_llm: template rationale")

        meta = _chunk_meta(db, [c.chunk_id for c in assembled.chunks])
        picks.append({
            "item": card,
            "score": round(score, 4),
            "score_parts": {
                "retrieval": round(base, 4),
                "taste": round(taste[item_id], 4) if item_id in taste else None,
                "completion_boost": round(w_comp * gain / 100.0, 4),
            },
            "completion": [asdict(d) for d in deltas.get(item_id, [])],
            "rationale": {
                "text": out["answer"],
                "generator": generator,
                "citations": [
                    {
                        "n": c.citation_id, "chunk_id": c.chunk_id, "item_id": c.item_id,
                        "title": c.title, "year": c.year,
                        "section_name": meta.get(c.chunk_id, {}).get("section_name"),
                        "source": meta.get(c.chunk_id, {}).get("source"),
                        "snippet": _snippet(c.text, 240),
                    }
                    for c in assembled.chunks
                ],
                "groundedness": out["groundedness"],
                "facts": facts,
            },
        })

    response = {
        "query": query,
        "parsed": parsed.to_dict(),
        "mode_used": mode,
        "degraded": degraded,
        "excluded_unknown_runtime": _count_unknown_runtime(db, filters),
        "picks": picks,
        "empty": None,
    }
    if not picks:
        response["empty"] = _explain_empty(db, parsed, scope, residual, model, mode, director_ids)
    return response


def _explain_empty(
    db: Database, parsed: ParsedQuery, scope: str, residual: str, model: Any, mode: str,
    director_ids: list[int],
) -> dict:
    """Say which active constraint, if relaxed, would bring results back."""
    base = to_search_filters(parsed, scope, item_ids=director_ids or None)
    groups = {
        "runtime": ("runtime_min", "runtime_max"),
        "decade": ("decade",),
        "years": ("year_min", "year_max"),
        "status": ("seen", "on_watchlist"),
    }
    relax = []
    for name, fields in groups.items():
        if all(getattr(base, f) is None for f in fields):
            continue
        relaxed = SearchFilters(**{**base.__dict__, **{f: None for f in fields}})
        if residual:
            n = len(search(db, residual, model=model, mode=mode, limit=5, filters=relaxed))
        else:
            n = len(_filter_only_candidates(db, relaxed, 5))
        if n:
            relax.append({"filter": name, "would_match": n})
    return {"message": "Nothing in your index matches all of those constraints.", "relax": relax}
