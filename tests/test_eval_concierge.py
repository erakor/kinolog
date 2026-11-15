"""Tests for the concierge eval suite (fixture DB, no model, no network)."""

import pytest

from kinolog.core.chunkers import chunk_document
from kinolog.core.db import Database
from kinolog.core.taste import TasteScore
from kinolog.eval.concierge import (
    eval_concierge,
    eval_concierge_hearts,
    load_concierge_prompts,
    violates,
)
from kinolog.eval.harness import log_results


@pytest.fixture
def db():
    d = Database(":memory:")
    ann = d.upsert_person("Ann Auteur", tmdb_person_id=1)
    rows = [
        ("Quiet Harbor", 1962, 95, 0, "A fisherman endures a slow winter in a harbor town."),
        ("Paper Moon Rising", 1964, 110, 0, "A con artist and a child cross the plains."),
        ("The Long Corridor", 1966, 150, 1,
         "Detectives chase a missing ledger through a hospital."),
        ("Brief Encounter Again", 1985, 80, 1, "Two strangers meet on a train platform each week."),
        ("Midnight Ferry", 2010, 100, 0, "A ferry crossing turns into a tense mystery."),
    ]
    for title, year, rt, seen, text in rows:
        i = d.upsert_item("film", title, year, runtime_min=rt)
        d.upsert_credit(i, ann, "Director", "Directing")
        d.upsert_user_status(i, seen=seen)
        body = f"{title} ({year})\nGenres: Drama\nRuntime: {rt} minutes\n\n{text}"
        doc = d.upsert_document(i, "tmdb", "en", body)
        chunk_document(d, doc, strategy="whole")
    yield d
    d.close()


PROMPTS = [
    {"query": "a tense mystery under 105 minutes", "expected_filters": {"runtime_max": 105},
     "relevant": [{"title": "Midnight Ferry", "year": 2010}], "acceptable": []},
    {"query": "slow drama from the 60s", "expected_filters": {"decade": 1960},
     "relevant": [{"title": "Quiet Harbor", "year": 1962}],
     "acceptable": [{"title": "Paper Moon Rising", "year": 1964}]},
    {"query": "a film from my watchlist", "expected_filters": {"on_watchlist": True},
     "relevant": [], "acceptable": []},
]


def by_name(results):
    return {r.metric: r for r in results}


def test_suite_runs_and_reports_expected_metrics(db):
    results = by_name(eval_concierge(db, prompts=PROMPTS, scope="all"))
    assert {"parser_exact_match", "parser_field_accuracy", "constraint_satisfaction",
            "hit@1", "hit@3", "hit@5", "mrr", "ndcg@5",
            "rationale_groundedness", "citation_validity"} <= set(results)
    assert all(r.suite == "concierge" for r in results.values())
    assert results["parser_exact_match"].value == 1.0
    assert results["constraint_satisfaction"].value == 1.0
    assert results["hit@5"].value == 1.0
    assert results["citation_validity"].value == 1.0


def test_wrong_expectation_lowers_parser_score(db):
    bad = [{"query": "under 90 minutes", "expected_filters": {"runtime_max": 60}}]
    r = by_name(eval_concierge(db, prompts=bad))
    assert r["parser_exact_match"].value == 0.0 and r["parser_field_accuracy"].value < 1.0


def test_results_are_logged_to_eval_runs(db):
    log_results(db, eval_concierge(db, prompts=PROMPTS))
    rows = db.execute("SELECT DISTINCT suite FROM eval_runs").fetchall()
    assert [r["suite"] for r in rows] == ["concierge"]


def test_violates_detects_each_constraint(db):
    from kinolog.core.search import SearchFilters

    card = {"runtime_min": 100, "year": 1962,
            "status": {"seen": True, "on_watchlist": False}}
    assert violates(card, SearchFilters(runtime_max=90)) == ["runtime_max"]
    assert violates(card, SearchFilters(decade=1970)) == ["decade"]
    assert violates(card, SearchFilters(seen=False)) == ["seen"]
    unknown = {**card, "runtime_min": None}
    assert violates(unknown, SearchFilters(runtime_max=90)) == ["runtime_unknown"]
    assert violates(card, SearchFilters(runtime_max=120, decade=1960, seen=True)) == []


def test_empty_prompts_return_nothing(db):
    assert eval_concierge(db, prompts=[]) == []


def test_default_dataset_loads():
    data = load_concierge_prompts()
    assert data and all("query" in p and "expected_filters" in p for p in data)


def test_hearts_check_shows_taste_weight_lifts_heldout_hearts():
    d = Database(":memory:")
    liked_ids = set()
    for n in range(24):
        liked = n >= 14  # ten hearts, created after the ten non-hearts
        i = d.upsert_item("film", f"Drama Number {n:02d}", 2000 + n % 10, runtime_min=100)
        d.upsert_user_status(i, seen=1 if liked else 0, liked=int(liked))
        text = f"Drama Number {n:02d}\nGenres: Drama\n\nSame text."
        doc = d.upsert_document(i, "tmdb", "en", text)
        chunk_document(d, doc, strategy="whole")
        if liked:
            liked_ids.add(i)

    def ranker(db_, ids, train):
        return [TasteScore(i, 1.0 if i in liked_ids else 0.0, method="fake") for i in ids]

    with_taste = by_name(eval_concierge_hearts(d, ranker, w_taste=1.0, n_splits=3, seed=1))
    without = by_name(eval_concierge_hearts(d, ranker, w_taste=0.0, n_splits=3, seed=1))
    assert with_taste["hearts_hit@5"].value == 1.0
    assert with_taste["hearts_hit@5"].value >= without["hearts_hit@5"].value
    assert with_taste["hearts_hit@5"].stdev is not None
    d.close()


def test_hearts_check_needs_enough_hearts(db):
    assert eval_concierge_hearts(db, lambda *a: []) == []
