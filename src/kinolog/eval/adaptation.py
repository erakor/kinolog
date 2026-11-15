"""Adaptation pair evaluation: measure cross-modal retrieval between books and their film adaptations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from kinolog.eval.harness import EvalResult
from kinolog.store import Database

logger = logging.getLogger(__name__)


@dataclass
class AdaptationPair:
    book_id: int
    book_title: str
    film_id: int
    film_title: str


def find_adaptation_pairs(db: Database) -> list[AdaptationPair]:
    """
    Find matching book and film pairs in the database.
    Checks for identical or normalized titles between book and film items.
    """
    books = db.get_items(item_type="book")
    films = db.get_items(item_type="film")

    film_by_title = {f["title"].lower().strip(): f for f in films}
    pairs = []

    for b in books:
        title_lower = b["title"].lower().strip()
        if title_lower in film_by_title:
            f = film_by_title[title_lower]
            pairs.append(AdaptationPair(
                book_id=b["id"],
                book_title=b["title"],
                film_id=f["id"],
                film_title=f["title"],
            ))

    return pairs


def eval_adaptation_pairs(
    db: Database,
    search_fn: Callable,
    pairs: list[AdaptationPair] | None = None,
) -> list[EvalResult]:
    """
    Evaluate adaptation retrieval in both directions:
    1. Query with book title/description -> rank of the film adaptation
    2. Query with film title/description -> rank of the source book
    """
    if pairs is None:
        pairs = find_adaptation_pairs(db)

    if not pairs:
        logger.warning("No adaptation pairs found in the database")
        return []

    book_to_film_ranks = []
    film_to_book_ranks = []

    for pair in pairs:
        # Book -> Film: Search with book title, filter or look for film
        b2f_results = search_fn(pair.book_title, item_type="film")
        result_film_ids = [r.item_id for r in b2f_results]
        if pair.film_id in result_film_ids:
            book_to_film_ranks.append(result_film_ids.index(pair.film_id) + 1)
        else:
            book_to_film_ranks.append(999)

        # Film -> Book: Search with film title, look for book
        f2b_results = search_fn(pair.film_title, item_type="book")
        result_book_ids = [r.item_id for r in f2b_results]
        if pair.book_id in result_book_ids:
            film_to_book_ranks.append(result_book_ids.index(pair.book_id) + 1)
        else:
            film_to_book_ranks.append(999)

    # Compute MRR for both directions
    b2f_mrr = sum(1.0 / r for r in book_to_film_ranks if r < 999) / len(pairs)
    f2b_mrr = sum(1.0 / r for r in film_to_book_ranks if r < 999) / len(pairs)
    b2f_hit5 = sum(1 for r in book_to_film_ranks if r <= 5) / len(pairs)
    f2b_hit5 = sum(1 for r in film_to_book_ranks if r <= 5) / len(pairs)

    return [
        EvalResult(suite="adaptation", metric="book_to_film_hit@5", value=b2f_hit5, config={"n_pairs": len(pairs)}),
        EvalResult(suite="adaptation", metric="book_to_film_mrr", value=b2f_mrr, config={"n_pairs": len(pairs)}),
        EvalResult(suite="adaptation", metric="film_to_book_hit@5", value=f2b_hit5, config={"n_pairs": len(pairs)}),
        EvalResult(suite="adaptation", metric="film_to_book_mrr", value=f2b_mrr, config={"n_pairs": len(pairs)}),
    ]
