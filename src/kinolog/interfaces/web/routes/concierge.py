from __future__ import annotations

from fastapi import APIRouter, Depends

from kinolog import services
from kinolog.features.concierge import parse_constraints
from kinolog.interfaces.web.deps import get_db, get_state
from kinolog.interfaces.web.schemas import ConciergeBody, ParseBody
from kinolog.interfaces.web.state import AppState
from kinolog.store import Database

router = APIRouter(prefix="/api/concierge")


@router.get("/suggestions")
def suggestions(db: Database = Depends(get_db)):
    return services.concierge_suggestions(db)


@router.post("/parse")
def parse(body: ParseBody):
    return parse_constraints(body.query).to_dict()


@router.get("/overview")
def overview(db: Database = Depends(get_db)):
    """Numbers and the completion radar for the Concierge home screen."""
    return services.concierge_overview(db)


@router.post("")
def concierge(body: ConciergeBody, state: AppState = Depends(get_state)):
    # Load the model (slow, first time only) before taking the DB lock.
    model = state.get_model() if state.db.vec_available else None
    with state.db_lock:
        return services.concierge_pick(
            state.db,
            body.query,
            model=model,
            scope=body.scope,
            limit=body.limit,
            generator_fn=state.generator,
            taste_fn=lambda ids: state.taste_cache.scores(state.db, ids),
            w_taste=state.w_taste,
            w_comp=state.w_comp,
        )
