"""Tests for core taste_scores (unavailable reasons and success path, no embeddings needed)."""

import pytest

from src.core import taste
from src.core.db import Database
from src.core.taste import TasteScore, TasteUnavailableError, taste_scores


@pytest.fixture
def db():
    d = Database(":memory:")
    a = d.upsert_item("film", "A", 2000)
    b = d.upsert_item("film", "B", 2001)
    d.upsert_user_status(a, liked=1)
    yield d, a, b
    d.close()


@pytest.fixture
def available(monkeypatch):
    monkeypatch.setattr(taste, "taste_available", lambda db, model_name="bge_m3": True)


def test_unavailable_without_vectors(db):
    d, a, b = db
    if d.vec_available:
        pytest.skip("sqlite-vec loaded; table check covers this")
    with pytest.raises(TasteUnavailableError, match="not available"):
        taste_scores(d, [b])


def test_unknown_ranker(db):
    d, a, b = db
    with pytest.raises(TasteUnavailableError, match="Unknown ranker"):
        taste_scores(d, [b], ranker="nope")


def test_no_hearts(available):
    d = Database(":memory:")
    i = d.upsert_item("film", "A", 2000)
    with pytest.raises(TasteUnavailableError, match="hearted"):
        taste_scores(d, [i])


def test_success_and_explicit_hearts(db, available, monkeypatch):
    d, a, b = db
    seen = {}

    def fake(db_, cands, hearts, **kw):
        seen["hearts"] = hearts
        return [TasteScore(i, 0.5, method="fake") for i in cands]

    monkeypatch.setitem(taste.RANKERS, "nearest_exemplar", fake)
    assert taste_scores(d, [b]) == {b: 0.5} and seen["hearts"] == [a]
    taste_scores(d, [b], heart_ids=[b])
    assert seen["hearts"] == [b]


def test_ranker_errors_and_empty_scores_are_wrapped(db, available, monkeypatch):
    d, a, b = db

    def boom(*args, **kw):
        raise RuntimeError("no such table: vec_bge_m3")

    monkeypatch.setitem(taste.RANKERS, "nearest_exemplar", boom)
    with pytest.raises(TasteUnavailableError, match="embeddings"):
        taste_scores(d, [b])
    monkeypatch.setitem(taste.RANKERS, "nearest_exemplar", lambda *a, **k: [])
    with pytest.raises(TasteUnavailableError, match="No embeddings"):
        taste_scores(d, [b])
