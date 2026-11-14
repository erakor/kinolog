from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.db import Database
from src.interfaces.web.deps import get_db

router = APIRouter(prefix="/api/items")


@router.get("/lookup")
def lookup(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(8, ge=1, le=25),
    db: Database = Depends(get_db),
):
    return db.find_items_by_title(q, limit=limit)


@router.get("/{item_id}")
def get_item(item_id: int, db: Database = Depends(get_db)):
    card = db.get_item_card(item_id)
    if card is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such item"})
    rows = db.execute(
        "SELECT DISTINCT source FROM documents WHERE item_id = ? ORDER BY source", (item_id,)
    ).fetchall()
    return {**card, "sources": [r["source"] for r in rows]}
