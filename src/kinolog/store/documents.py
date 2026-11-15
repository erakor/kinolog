"""Documents and chunks."""

from __future__ import annotations

from kinolog.store.util import content_hash


class DocumentsMixin:
    def upsert_document(
        self,
        item_id: int,
        source: str,
        lang: str,
        text: str,
    ) -> int:
        """Insert or update a document. Returns document id."""
        c_hash = content_hash(text)
        row = self.conn.execute(
            "SELECT id, content_hash FROM documents WHERE item_id = ? AND source = ? AND lang = ?",
            (item_id, source, lang),
        ).fetchone()

        if row:
            if row["content_hash"] == c_hash:
                return row["id"]  # unchanged
            self.conn.execute(
                "UPDATE documents SET text = ?, content_hash = ? WHERE id = ?",
                (text, c_hash, row["id"]),
            )
            self.conn.commit()
            return row["id"]

        cur = self.conn.execute(
            "INSERT INTO documents (item_id, source, lang, text, content_hash) VALUES (?, ?, ?, ?, ?)",
            (item_id, source, lang, text, c_hash),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def upsert_chunk(
        self,
        item_id: int,
        document_id: int,
        strategy: str,
        ord: int,
        text: str,
        section_name: str | None = None,
        lang: str | None = None,
        token_count: int | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> int:
        """Insert or update a chunk. Returns chunk id."""
        c_hash = content_hash(text)
        row = self.conn.execute(
            "SELECT id, content_hash FROM chunks WHERE document_id = ? AND strategy = ? AND ord = ?",
            (document_id, strategy, ord),
        ).fetchone()

        if row:
            if row["content_hash"] == c_hash:
                return row["id"]
            self.conn.execute(
                """UPDATE chunks SET item_id=?, text=?, section_name=?, lang=?,
                   token_count=?, start_ms=?, end_ms=?, content_hash=? WHERE id=?""",
                (item_id, text, section_name, lang, token_count, start_ms, end_ms, c_hash, row["id"]),
            )
            self.conn.commit()
            return row["id"]

        cur = self.conn.execute(
            """INSERT INTO chunks (item_id, document_id, strategy, ord, section_name,
               lang, text, token_count, start_ms, end_ms, content_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_id, document_id, strategy, ord, section_name, lang, text,
             token_count, start_ms, end_ms, c_hash),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def delete_chunks_for_document(self, document_id: int, strategy: str | None = None):
        """Delete chunks for a document, optionally filtered by strategy."""
        if strategy:
            self.conn.execute(
                "DELETE FROM chunks WHERE document_id = ? AND strategy = ?",
                (document_id, strategy),
            )
        else:
            self.conn.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))
        self.conn.commit()
