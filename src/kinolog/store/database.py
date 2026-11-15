"""The Database facade: one class assembled from per-aggregate mixins."""

from __future__ import annotations

from kinolog.store.connection import ConnectionBase
from kinolog.store.documents import DocumentsMixin
from kinolog.store.eval_runs import EvalRunsMixin
from kinolog.store.ingest_meta import IngestMetaMixin
from kinolog.store.items import ItemsMixin
from kinolog.store.people import PeopleMixin
from kinolog.store.ratings import RatingsMixin
from kinolog.store.user_state import UserStateMixin
from kinolog.store.vectors import VectorsMixin
from kinolog.store.views import ViewsMixin


class Database(
    ItemsMixin,
    DocumentsMixin,
    PeopleMixin,
    RatingsMixin,
    IngestMetaMixin,
    UserStateMixin,
    ViewsMixin,
    EvalRunsMixin,
    VectorsMixin,
    ConnectionBase,
):
    """SQLite database with FTS5 and optional sqlite-vec support.

    Methods live in the mixins, one per aggregate; they all operate on ``self.conn``.
    """
