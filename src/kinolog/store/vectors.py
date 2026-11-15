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

    def upsert_embedding(
        self, model_name: str, chunk_id: int, embedding: bytes, commit: bool = True
    ) -> None:
        """Store one chunk's embedding (float32 bytes) in the model's vec table.

        Pass ``commit=False`` inside a batch and commit once per batch.
        """
        self.conn.execute(
            f"INSERT OR REPLACE INTO vec_{model_name} (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, embedding),
        )
        if commit:
            self.conn.commit()
