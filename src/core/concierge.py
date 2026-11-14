"""Concierge: deterministic constraint parsing, filtered retrieval and grounded picks.

The parser is regex + small lexicons (no LLM) so it is testable and works offline.
Matched constraint phrases are removed from the residual query, because the BM25 index
contains literal text like "Runtime: 90 minutes" that such phrases would otherwise match.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from src.core.search import SearchFilters

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
    return ParsedQuery(residual_query=residual, filters=filters, chips=chips, unparsed=unparsed)


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
