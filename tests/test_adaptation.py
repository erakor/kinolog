"""Tests for adaptation pairs evaluation."""

import pytest
from kinolog.core.db import Database
from kinolog.core.chunkers import chunk_document
from kinolog.core.search import search_bm25, SearchFilters
from kinolog.eval.adaptation import find_adaptation_pairs, eval_adaptation_pairs, AdaptationPair


@pytest.fixture
def db_with_adaptations():
    db = Database(":memory:")

    # Add book and film of Solaris
    b_id = db.upsert_item("book", "Solaris", 1961)
    doc_b = db.upsert_document(b_id, "openlibrary", "en", "Solaris (1961)\nScience fiction novel by Stanislaw Lem about cosmonauts on Solaris station.")
    chunk_document(db, doc_b, strategy="whole")

    f_id = db.upsert_item("film", "Solaris", 1972)
    doc_f = db.upsert_document(f_id, "tmdb", "en", "Solaris (1972)\nFilm directed by Andrei Tarkovsky based on the novel by Stanislaw Lem.")
    chunk_document(db, doc_f, strategy="whole")

    # Add book and film of Le Mépris / Contempt
    b_id2 = db.upsert_item("book", "Le Mépris", 1954)
    doc_b2 = db.upsert_document(b_id2, "openlibrary", "fr", "Le Mépris (1954)\nRoman d'Alberto Moravia.")
    chunk_document(db, doc_b2, strategy="whole")

    f_id2 = db.upsert_item("film", "Le Mépris", 1963)
    doc_f2 = db.upsert_document(f_id2, "tmdb", "fr", "Le Mépris (1963)\nFilm de Jean-Luc Godard adapté du roman d'Alberto Moravia.")
    chunk_document(db, doc_f2, strategy="whole")

    yield db
    db.close()


def test_find_adaptation_pairs(db_with_adaptations):
    pairs = find_adaptation_pairs(db_with_adaptations)
    assert len(pairs) == 2
    titles = {p.film_title for p in pairs}
    assert "Solaris" in titles
    assert "Le Mépris" in titles


def test_eval_adaptation_pairs(db_with_adaptations):
    def search_fn(query, item_type=None):
        filters = SearchFilters(item_type=item_type)
        return search_bm25(db_with_adaptations, query, limit=5, filters=filters)

    results = eval_adaptation_pairs(db_with_adaptations, search_fn)
    assert len(results) == 4
    metrics = {r.metric: r.value for r in results}
    assert metrics["book_to_film_hit@5"] == 1.0
    assert metrics["film_to_book_hit@5"] == 1.0
