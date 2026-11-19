"""Tests for evaluation metrics."""

import pytest

from kinolog.eval.metrics import hit_at_k, mrr, recall_at_k
from kinolog.rag.grounding import groundedness


def test_recall_at_k():
    ranked = [1, 2, 3, 4, 5]
    relevant = {2, 4, 6}
    assert recall_at_k(ranked, relevant, 5) == pytest.approx(2 / 3)
    assert recall_at_k(ranked, relevant, 2) == pytest.approx(1 / 3)


def test_recall_at_k_empty():
    assert recall_at_k([1, 2], set(), 5) == 0.0


def test_hit_at_k():
    ranked = [10, 20, 30, 40, 50]
    assert hit_at_k(ranked, 30, 5) == 1
    assert hit_at_k(ranked, 30, 2) == 0
    assert hit_at_k(ranked, 99, 5) == 0


def test_mrr():
    ranked = [10, 20, 30, 40]
    assert mrr(ranked, {30}) == pytest.approx(1 / 3)
    assert mrr(ranked, {10}) == pytest.approx(1.0)
    assert mrr(ranked, {99}) == 0.0


def test_mrr_multiple_relevant():
    ranked = [10, 20, 30]
    # MRR is 1/rank of FIRST relevant
    assert mrr(ranked, {20, 30}) == pytest.approx(1 / 2)


def test_groundedness():
    assert groundedness([1, 2, 3], {1, 2, 3, 4}) == 1.0
    assert groundedness([1, 2, 3], {1, 2}) == pytest.approx(2 / 3)
    assert groundedness([], {1, 2}) == 1.0  # vacuously true
