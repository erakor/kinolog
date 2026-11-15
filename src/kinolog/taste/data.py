"""Reading item embeddings, hearts and candidates from the store."""

from __future__ import annotations

from typing import Any

from kinolog.config import DEFAULT_MODEL, DEFAULT_STRATEGY
from kinolog.store import Database

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore


def _get_item_embeddings(
    db: Database,
    item_ids: list[int],
    model_name: str = DEFAULT_MODEL,
    strategy: str = DEFAULT_STRATEGY,
    rollup: str = "mean",
) -> dict[int, Any]:
    """
    Get a single embedding per item, aggregated from its chunks.

    rollup: "mean", "max", or "first"
    """
    if np is None:
        raise RuntimeError("numpy is required for embedding-based taste ranking")
    vec_table = f"vec_{model_name}"
    result = {}

    for item_id in item_ids:
        rows = db.execute(
            f"""SELECT v.embedding FROM {vec_table} v
                JOIN chunks c ON v.chunk_id = c.id
                WHERE c.item_id = ? AND c.strategy = ?
                ORDER BY c.ord""",
            (item_id, strategy),
        ).fetchall()

        if not rows:
            continue

        embeddings = np.array([
            np.frombuffer(row["embedding"], dtype=np.float32)
            for row in rows
        ])

        if rollup == "mean":
            vec = embeddings.mean(axis=0)
        elif rollup == "max":
            vec = embeddings.max(axis=0)
        elif rollup == "first":
            vec = embeddings[0]
        else:
            vec = embeddings.mean(axis=0)

        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        result[item_id] = vec

    return result


def _get_heart_ids(db: Database, first_heart_date: str | None = None) -> list[int]:
    """Get item IDs of hearted films."""
    rows = db.execute(
        "SELECT item_id FROM user_status WHERE liked = 1"
    ).fetchall()
    return [r["item_id"] for r in rows]


def _get_candidate_ids(
    db: Database,
    first_heart_date: str | None = None,
    exclude_ids: set[int] | None = None,
    item_type: str = "film",
) -> list[int]:
    """Get candidate item IDs for taste ranking."""
    rows = db.execute(
        "SELECT id FROM items WHERE item_type = ?", (item_type,)
    ).fetchall()
    ids = [r["id"] for r in rows]
    if exclude_ids:
        ids = [i for i in ids if i not in exclude_ids]
    return ids
