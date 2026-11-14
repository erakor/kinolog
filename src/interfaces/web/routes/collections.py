from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core import collections as coll
from src.core.db import Database
from src.interfaces.web.deps import get_db

router = APIRouter(prefix="/api/collections")


def _summary(d: coll.DirectorCompletion, *, with_films: bool) -> dict:
    out = {k: v for k, v in asdict(d).items() if k != "films"}
    if with_films:
        out["films"] = [asdict(f) for f in (d.films or [])]
    return out


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
    allc = coll.director_completion(db, sort=sort, status=status, q=q, min_films=min_films)
    page = allc[offset:offset + limit]
    if include_films:
        coll.attach_films(db, page)
    return {
        "total": len(allc),
        "summary": coll.collection_summary(db, min_films=min_films),
        "items": [_summary(d, with_films=include_films) for d in page],
    }


@router.get("/directors/{person_id}")
def director(person_id: int, db: Database = Depends(get_db)):
    d = coll.director_detail(db, person_id)
    if d is None:
        raise HTTPException(404, {"code": "not_found", "message": "No such director"})
    out = _summary(d, with_films=True)
    for f in out["films"]:
        f["after_pct"] = None if f["seen"] else coll.pct(d.seen + 1, d.total)
    return out
