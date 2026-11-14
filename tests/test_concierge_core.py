"""Tests for the Concierge constraint parser."""

import pytest

from src.core.concierge import parse_constraints, to_search_filters

CASES = [
    # text, expected filters (subset), expected residual
    ("I have 90 minutes. Give me a movie.", {"runtime_max": 90}, ""),
    ("under 1h30", {"runtime_max": 90}, ""),
    ("less than 1h 45m please", {"runtime_max": 105}, ""),
    ("under two hours", {"runtime_max": 120}, ""),
    ("something under 2 hours", {"runtime_max": 120}, ""),
    ("at least 2 hours", {"runtime_min": 120}, ""),
    ("longer than 150 minutes", {"runtime_min": 150}, ""),
    ("I have an hour", {"runtime_max": 60}, ""),
    ("an hour and a half", {"runtime_max": 90}, ""),
    ("1.5 hours", {"runtime_max": 90}, ""),
    ("<= 100 min", {"runtime_max": 100}, ""),
    ("something short", {"runtime_max": 100}, ""),
    ("a short comedy", {"runtime_max": 100}, "comedy"),
    ("slow drama from the 60s", {"decade": 1960}, "slow drama"),
    ("1960s thriller", {"decade": 1960}, "thriller"),
    ("a film from the sixties", {"decade": 1960}, ""),
    ("'70s paranoia", {"decade": 1970}, "paranoia"),
    ("2010s horror", {"decade": 2010}, "horror"),
    ("before 1970", {"year_max": 1969}, ""),
    ("after 2000 sci-fi", {"year_min": 2001}, "sci-fi"),
    ("since 1990", {"year_min": 1990}, ""),
    ("made in 1962", {"year_min": 1962, "year_max": 1962}, "made"),
    ("between 1960 and 1970", {"year_min": 1960, "year_max": 1970}, ""),
    ("movies I haven't seen", {"seen": False}, ""),
    ("not seen yet", {"seen": False}, ""),
    ("something already seen", {"seen": True}, ""),
    ("from my watchlist", {"on_watchlist": True}, ""),
    ("quiet comfort film in my watch list", {"on_watchlist": True}, "quiet comfort"),
    ("a tense Italian thriller", {}, "tense Italian thriller"),
    ("tense and sharp under 2 hours", {"runtime_max": 120}, "tense sharp"),
    ("journalist in Rome", {}, "journalist Rome"),
]


@pytest.mark.parametrize("text,expected,residual", CASES)
def test_parse_table(text, expected, residual):
    p = parse_constraints(text)
    for k, v in expected.items():
        assert p.filters.get(k) == v, (text, p.filters)
    # no unexpected runtime/decade/year constraints
    for k in ("runtime_max", "runtime_min", "decade", "year_min", "year_max"):
        if k not in expected:
            assert k not in p.filters, (text, p.filters)
    assert p.residual_query == residual


def test_runtime_text_removed_from_residual():
    p = parse_constraints("slow italian drama under 100 minutes")
    assert "minutes" not in p.residual_query and "100" not in p.residual_query
    assert p.residual_query == "slow italian drama"
    assert p.unparsed == ["language: italian"]


def test_chips_have_spans_and_labels():
    text = "drama under 90 minutes from the 60s"
    p = parse_constraints(text)
    labels = {c.kind: c.label for c in p.chips}
    assert labels["runtime_max"] == "≤ 90 min" and labels["decade"] == "1960s"
    for c in p.chips:
        assert 0 <= c.source_span[0] < c.source_span[1] <= len(text)
    d = p.to_dict()
    assert d["chips"][0]["source_span"][0] >= 0


def test_decade_not_mistaken_for_runtime_or_year():
    p = parse_constraints("90s action")
    assert p.filters == {"decade": 1990} and p.residual_query == "action"


def test_to_search_filters_scope_and_override():
    p = parse_constraints("drama under 90 minutes")
    f = to_search_filters(p, "unseen")
    assert f.item_type == "film" and f.seen is False and f.runtime_max == 90
    assert to_search_filters(p, "watchlist").on_watchlist is True
    assert to_search_filters(p, "all").seen is None
    p2 = parse_constraints("something already seen")
    assert to_search_filters(p2, "unseen").seen is True
    p3 = parse_constraints("a book about rome")
    assert to_search_filters(p3).item_type == "film"  # v1 is films only


def test_empty_and_symbol_only_input():
    p = parse_constraints("")
    assert p.residual_query == "" and p.filters == {} and p.chips == []
    assert parse_constraints("???").residual_query == ""
