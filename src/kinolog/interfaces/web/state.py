"""Shared application state: DB handle, serialization lock, lazy embedding model."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from kinolog.core import taste as taste_core
from kinolog.core.db import Database

logger = logging.getLogger(__name__)


class AppState:
    def __init__(
        self,
        db: Database,
        *,
        load_model: bool = True,
        generator: Callable[[str, str], str] | None = None,
        w_taste: float = 0.0,
        w_comp: float = 0.0,
    ):
        self.db = db
        # One SQLite connection is shared across worker threads, so all DB use is serialized.
        # A plain Lock (not RLock) because FastAPI may release it from a different thread.
        self.db_lock = threading.Lock()
        self.load_model = load_model
        self.generator = generator
        # Rerank weights stay 0 (pure retrieval) until `eval concierge` justifies more.
        self.w_taste = w_taste
        self.w_comp = w_comp
        self.taste_cache: dict[Any, Any] = {}
        self._model: Any = None
        self._model_tried = False
        self._model_lock = threading.Lock()

    def get_model(self) -> Any:
        """Lazy-load the embedding model; None if disabled or unavailable."""
        if not self.load_model:
            return None
        with self._model_lock:
            if not self._model_tried:
                self._model_tried = True
                try:
                    from kinolog.core.embed import BGE_M3

                    self._model = BGE_M3()
                except Exception as e:  # missing deps, no weights, no network
                    logger.warning("Embedding model not available: %s", e)
        return self._model

    @property
    def model_loaded(self) -> bool:
        return self._model is not None

    def taste_available(self) -> bool:
        return taste_core.taste_available(self.db)

    def invalidate(self) -> None:
        """Call after any mutation that can change taste inputs."""
        self.taste_cache.clear()
