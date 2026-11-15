"""sqlite-vec tables."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class VectorsMixin:
    def try_create_vec_table(self, model_name: str, dim: int) -> bool:
        """Create a vec0 table for a given model. Returns True if created, False if vec not available."""
        if not self._vec_available:
            logger.warning("Cannot create vec table: sqlite-vec not loaded")
            return False
        table_name = f"vec_{model_name}"
        sql = f"CREATE VIRTUAL TABLE IF NOT EXISTS {table_name} USING vec0(chunk_id INTEGER PRIMARY KEY, embedding float[{dim}])"
        self.conn.execute(sql)
        self.conn.commit()
        logger.info("Created vector table %s (dim=%d)", table_name, dim)
        return True
