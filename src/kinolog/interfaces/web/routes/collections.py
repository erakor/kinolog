from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from kinolog import services
from kinolog.interfaces.web.deps import get_db
from kinolog.store import Database

router = APIRouter(prefix="/api/collections")


@router.get("/directors")
def list_directors(
    sort: str = "pct",
    status: str = "all",
    q: str | None = None,
    min_films: int = Query(2, ge=1, le=50),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_films: bool = False,
    db: Database = Depends(get_db),
):
    return services.directors_view(
        db,
        sort=sort,
        status=status,
        q=q,
        min_films=min_films,
        limit=limit,
        offset=offset,
        include_films=include_films,
    )


@router.get("/directors/{person_id}")
def director(person_id: int, db: Database = Depends(get_db)):
    return services.director_view(db, person_id)
