from __future__ import annotations

from fastapi import APIRouter, Depends

from src.core.db import Database
from src.interfaces.web.deps import get_db, get_state
from src.interfaces.web.state import AppState

router = APIRouter()


@router.get("/api/health")
def health(state: AppState = Depends(get_state), db: Database = Depends(get_db)):
    stats = db.stats()
    return {
        "ok": True,
        "vec_available": db.vec_available,
        "model_enabled": state.load_model,
        "model_loaded": state.model_loaded,
        "llm_configured": state.generator is not None,
        "counts": {k: stats[k] for k in ("items", "chunks", "people", "credits", "watch_log")},
        "taste_available": state.taste_available(db),
    }
