"""Tests for the evaluation harness."""

import pytest
from kinolog.store import Database
from kinolog.core.chunkers import chunk_document
from kinolog.core.search import search_bm25
from kinolog.eval.harness import eval_known_items, eval_hearts_recall, log_results


@pytest.fixture
def db_for_eval():
    db = Database(":memory:")

    films = [
        ("La Dolce Vita", 1960, "film shot at Cinecittà with natural light Marcello Mastroianni as a journalist in Rome"),
        ("8½", 1963, "black and white film about a filmmaker's creative crisis and memories Fellini"),
        ("L'Avventura", 1960, "a woman wanders through a barren volcanic island looking for her vanished friend"),
        ("Le Mépris", 1963, "French New Wave couple arguing in an apartment long tracking shots Godard"),
        ("À bout de souffle", 1960, "Belmondo imitating Bogart jump cuts through Paris Godard"),
        ("Bicycle Thieves", 1948, "Italian neorealist film about a man searching for his stolen bicycle De Sica"),
        ("The Seventh Seal", 1957, "Bergman film about a knight playing chess with Death during the plague"),
        ("The Exterminating Angel", 1962, "surrealist dinner party that never ends Buñuel"),
        ("Solaris", 1972, "Tarkovsky film about a space station orbiting a sentient ocean"),
    ]

    for title, year, text in films:
        item_id = db.upsert_item("film", title, year)
        db.upsert_user_status(item_id, seen=1, liked=1 if year <= 1962 else 0)
        doc_id = db.upsert_document(item_id, "tmdb", "en", text)
        chunk_document(db, doc_id, strategy="whole")

    yield db
    db.close()


def test_eval_known_items(db_for_eval):
    queries = [
        {"query": "Cinecittà natural light journalist", "target_title": "La Dolce Vita", "target_year": 1960},
        {"query": "stolen bicycle Rome", "target_title": "Bicycle Thieves", "target_year": 1948},
    ]

    def search_fn(q):
        return search_bm25(db_for_eval, q, limit=10)

    results = eval_known_items(db_for_eval, search_fn, queries=queries)
    assert len(results) > 0

    metrics_map = {r.metric: r.value for r in results}
    assert "hit@5" in metrics_map
    assert metrics_map["hit@5"] == 1.0  # Both should be hit in top 5
    assert "mrr" in metrics_map
    assert metrics_map["mrr"] > 0.0

    # Test logging to database
    log_results(db_for_eval, results)
    logged = db_for_eval.execute("SELECT * FROM eval_runs").fetchall()
    assert len(logged) == len(results)


def test_eval_hearts_recall(db_for_eval):
    # Dummy ranker that returns candidates sorted by id
    from kinolog.core.taste import TasteScore

    def dummy_ranker(db, candidates, hearts):
        return [TasteScore(item_id=cid, score=float(-cid), method="dummy") for cid in candidates]

    results = eval_hearts_recall(
        db_for_eval,
        dummy_ranker,
        n_splits=3,
        holdout_fraction=0.3,
        k_values=(5, 10),
    )
    assert len(results) > 0
    metric_names = [r.metric for r in results]
    assert "recall@5" in metric_names
    assert "mrr" in metric_names
