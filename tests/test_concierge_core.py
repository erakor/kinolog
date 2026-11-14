"""Tests for the Concierge constraint parser."""

import pytest

from src.core.chunkers import chunk_document
from src.core.concierge import parse_constraints, pick, to_search_filters
from src.core.db import Database

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


# --- pick pipeline -----------------------------------------------------------------------



@pytest.fixture
def pdb():
    db = Database(":memory:")
    ann = db.upsert_person("Ann Auteur", tmdb_person_id=1)
    films = [
        ("Quiet Harbor", 1990, 95, True, True, False,
         "A fisherman endures a slow winter in a harbor town."),
        ("Paper Moon Rising", 1995, 110, True, False, False,
         "A con artist and a child cross the plains."),
        ("The Long Corridor", 2000, 150, False, False, True,
         "Detectives chase a missing ledger through a hospital."),
        ("Brief Encounter Again", 2005, 80, False, False, True,
         "Two strangers meet on a train platform each week."),
        ("Midnight Ferry", 2010, 100, False, False, False,
         "A ferry crossing turns into a tense mystery."),
        ("Mystery Unknown", 2011, None, False, False, False,
         "A tense mystery with no recorded runtime."),
    ]
    for title, year, rt, seen, liked, queued, text in films:
        i = db.upsert_item("film", title, year, runtime_min=rt)
        db.upsert_credit(i, ann, "Director", "Directing")
        db.upsert_user_status(i, seen=int(seen), liked=int(liked), on_watchlist=int(queued))
        body = f"{title} ({year})\nGenres: Drama\n" + (f"Runtime: {rt} minutes\n" if rt else "")
        doc = db.upsert_document(i, "tmdb", "en", body + "\n" + text)
        chunk_document(db, doc, strategy="whole")
    yield db
    db.close()


def test_pick_honors_hard_constraints(pdb):
    out = pick(pdb, "a tense mystery under 105 minutes I haven't seen")
    titles = [p["item"]["title"] for p in out["picks"]]
    assert titles == ["Midnight Ferry"]  # unknown-runtime film excluded, seen films excluded
    for p in out["picks"]:
        assert p["item"]["runtime_min"] <= 105 and not p["item"]["status"]["seen"]
    assert out["excluded_unknown_runtime"] == 1
    assert out["mode_used"] == "bm25"
    assert any(d.startswith("no_vector") or d.startswith("no_model") for d in out["degraded"])
    assert out["parsed"]["residual_query"] == "tense mystery"


def test_pick_template_rationale_is_grounded_and_cites_real_chunks(pdb):
    out = pick(pdb, "tense mystery")
    p = out["picks"][0]
    r = p["rationale"]
    assert r["generator"] == "template" and r["groundedness"] == 1.0
    assert r["citations"] and "[^1]" in r["text"]
    chunk_ids = {row["id"] for row in pdb.execute("SELECT id FROM chunks")}
    assert all(c["chunk_id"] in chunk_ids and c["snippet"] for c in r["citations"])
    labels = {f["label"] for f in r["facts"]}
    assert {"Director", "Completion"} <= labels
    assert p["completion"] and p["completion"][0]["name"] == "Ann Auteur"


def test_pick_empty_residual_ranks_watchlist_first(pdb):
    out = pick(pdb, "I have 120 minutes. Give me a movie.")
    titles = [p["item"]["title"] for p in out["picks"]]
    assert set(titles) <= {"Brief Encounter Again", "Midnight Ferry"}
    assert titles[0] == "Brief Encounter Again"  # on the watchlist
    assert out["parsed"]["residual_query"] == ""


def test_pick_named_director_and_completion_intent(pdb):
    out = pick(pdb, "What should I watch next from Ann Auteur?")
    assert out["picks"] and all(
        p["item"]["directors"][0]["name"] == "Ann Auteur" for p in out["picks"]
    )
    out2 = pick(pdb, "Help me finish a director I am close to completing")
    assert out2["parsed"]["intent"] == "completion" and out2["picks"]


def test_pick_empty_result_explains_which_filter(pdb):
    out = pick(pdb, "tense mystery under 30 minutes")
    assert out["picks"] == []
    assert out["empty"]["relax"][0]["filter"] == "runtime"


def test_llm_output_is_validated_and_falls_back(pdb):
    bad = pick(pdb, "tense mystery", generator_fn=lambda q, ctx: "Totally invented claim [^9].")
    assert bad["picks"][0]["rationale"]["generator"] == "template"
    assert any(d.startswith("llm_ungrounded") for d in bad["degraded"])

    def good(q, ctx):
        return "A tense ferry mystery [^1]."

    ok = pick(pdb, "tense mystery", generator_fn=good)
    assert ok["picks"][0]["rationale"]["generator"] == "llm"
    assert "no_llm: template rationale" not in ok["degraded"]


def test_llm_mentioning_candidate_not_in_context_falls_back(pdb):
    def other(q, ctx):
        return "Better is Paper Moon Rising [^1]."

    out = pick(pdb, "tense mystery", generator_fn=other)
    # Paper Moon Rising is in the index but not in the cited context: not grounded
    assert out["picks"][0]["rationale"]["generator"] == "template"
    assert any(d.startswith("llm_ungrounded") for d in out["degraded"])


def test_taste_weight_reorders_candidates(pdb):
    ids = {r["title"]: r["id"] for r in pdb.execute("SELECT id, title FROM items")}
    base = pick(pdb, "I have 200 minutes. Give me a movie.")
    assert base["picks"]
    taste = {ids["Midnight Ferry"]: 1.0}
    out = pick(pdb, "tense mystery", taste_fn=lambda c: taste, w_taste=5.0)
    assert out["picks"][0]["item"]["title"] == "Midnight Ferry"
    assert out["picks"][0]["score_parts"]["taste"] == 1.0


def test_taste_failure_degrades_gracefully(pdb):
    def boom(_c):
        raise RuntimeError("no vec table")

    out = pick(pdb, "tense mystery", taste_fn=boom, w_taste=1.0)
    assert out["picks"] and any(d.startswith("no_taste") for d in out["degraded"])


@pytest.mark.parametrize("text,key,value", [
    ("something to discover 90 minutes", "runtime_max", 90),
    ("admin 2 hours", "runtime_max", 120),
    ("at least 2 hours", "runtime_min", 120),
    ("minimum 100 minutes", "runtime_min", 100),
])
def test_qualifiers_need_word_boundaries(text, key, value):
    assert parse_constraints(text).filters == {key: value}


def test_two_digit_decade_not_taken_from_inside_a_longer_number():
    assert "decade" not in parse_constraints("1500s epics").filters
    assert parse_constraints("90s action").filters == {"decade": 1990}
