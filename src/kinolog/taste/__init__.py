"""Taste rankers: score items by taste affinity from hearted films.

``RANKERS`` maps a ranker name to its function; variants register themselves on import and are
all imported here so the registry is complete whichever module a caller imports first.
"""

from kinolog.taste import exemplar, mean, prototypes  # noqa: F401  (registers rankers)
from kinolog.taste.base import RANKERS, Ranker, register
from kinolog.taste.scores import (
    TasteScore,
    TasteUnavailableError,
    taste_available,
    taste_scores,
)

__all__ = [
    "RANKERS",
    "Ranker",
    "TasteScore",
    "TasteUnavailableError",
    "register",
    "taste_available",
    "taste_scores",
]
