"""The Concierge pick: constraints, retrieval, ranking and a grounded rationale."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from kinolog.features import collections as coll
from kinolog.features.concierge.constraints import (
    STOPWORDS,
    Chip,
    ParsedQuery,
    parse_constraints,
    to_search_filters,
)
from kinolog.features.concierge.rationale import (
    RATIONALE_TOKEN_BUDGET,
    _facts,
    _snippet,
    _template_text,
)
from kinolog.features.docfacts import item_facts
from kinolog.rag.context import assemble_context
from kinolog.rag.grounding import MentionScope, check_grounding
from kinolog.retrieval import SearchFilters, SearchResult, search
from kinolog.store import Database

CANDIDATE_LIMIT = 50


def _filter_only_candidates(db: Database, filters: SearchFilters) -> list[int]:
    """Candidate item ids from filters alone (no text query)."""
    item_cond, params = filters.to_sql_conditions()
    status_cond, sparams = filters.to_status_conditions()
    sql = "SELECT i.id FROM items i LEFT JOIN user_status us ON us.item_id = i.id"
    conds = [c for c in (item_cond, status_cond) if c]
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    rows = db.execute(sql + " LIMIT 5000", tuple(params + sparams)).fetchall()
    return [r["id"] for r in rows]


def _count_unknown_runtime(db: Database, filters: SearchFilters) -> int:
    if filters.runtime_min is None and filters.runtime_max is None:
        return 0
    relaxed = SearchFilters(**{**filters.__dict__, "runtime_min": None, "runtime_max": None})
    item_cond, params = relaxed.to_sql_conditions()
    status_cond, sparams = relaxed.to_status_conditions()
    conds = [c for c in (item_cond, status_cond, "i.runtime_min IS NULL") if c]
    row = db.execute(
        "SELECT COUNT(*) AS n FROM items i LEFT JOIN user_status us ON us.item_id = i.id"
        " WHERE " + " AND ".join(conds),
        tuple(params + sparams),
    ).fetchone()
    return row["n"]


def _director_item_ids(db: Database, query: str) -> tuple[str | None, list[int]]:
    """If the query names a director in the index, return (name, their counted films)."""
    rows = db.execute(
        "SELECT DISTINCT p.id, p.name FROM people p JOIN credits c ON c.person_id = p.id"
        " WHERE c.role = 'Director'"
    ).fetchall()
    low = query.lower()
    best = None
    for r in rows:
        name = r["name"]
        if len(name) >= 4 and name.lower() in low and (best is None or len(name) > len(best[1])):
            best = (r["id"], name)
    if not best:
        return None, []
    ids = db.execute(
        f"""SELECT DISTINCT i.id FROM credits c JOIN items i ON i.id = c.item_id
            WHERE c.person_id = ? AND c.role = 'Director' AND {coll.COUNTED}""",
        (best[0],),
    ).fetchall()
    return best[1], [r["id"] for r in ids]


def _mention_scope(db: Database) -> MentionScope:
    """Films whose titles are checked for mentions in a rationale.

    Every film in the index counts (so naming a film that is not in the cited context is
    caught), minus titles under 4 characters or that are plain stopwords ("M", "It", "Her"),
    which would match ordinary prose.
    """
    rows = db.execute("SELECT id, title FROM items WHERE item_type = 'film'").fetchall()
    return MentionScope(db, {
        r["id"] for r in rows
        if len(r["title"]) >= 4 and r["title"].lower() not in STOPWORDS
    })


def _chunk_meta(db: Database, chunk_ids: list[int]) -> dict[int, dict]:
    ids = [c for c in chunk_ids if c is not None]
    if not ids:
        return {}
    ph = ",".join("?" for _ in ids)
    rows = db.execute(
        f"""SELECT c.id, c.section_name, d.source FROM chunks c
            JOIN documents d ON d.id = c.document_id WHERE c.id IN ({ph})""",
        tuple(ids),
    ).fetchall()
    return {r["id"]: {"section_name": r["section_name"], "source": r["source"]} for r in rows}


def _item_chunks(
    db: Database, item_id: int, residual: str, model: Any, mode: str
) -> list[SearchResult]:
    """Most relevant chunks of one item (query-scoped), else its leading chunks."""
    if residual:
        found = search(
            db, residual, model=model, mode=mode, limit=3,
            filters=SearchFilters(item_ids=[item_id]), dedupe_items=False,
        )
        if found:
            return found
    item = db.get_item(item_id) or {}
    rows = db.execute(
        "SELECT id, text FROM chunks WHERE item_id = ? ORDER BY (strategy = 'whole') DESC, ord"
        " LIMIT 2",
        (item_id,),
    ).fetchall()
    return [
        SearchResult(
            item_id=item_id, chunk_id=r["id"], score=0.0, title=item.get("title", ""),
            year=item.get("year"), chunk_text=r["text"], source="chunk",
        )
        for r in rows
    ]


def _hearts_by_director(db: Database, person_id: int, exclude_item: int) -> int:
    row = db.execute(
        """SELECT COUNT(DISTINCT c.item_id) AS n FROM credits c
           JOIN user_status us ON us.item_id = c.item_id
           WHERE c.person_id = ? AND c.role = 'Director' AND us.liked = 1 AND c.item_id != ?""",
        (person_id, exclude_item),
    ).fetchone()
    return row["n"]


def pick(
    db: Database,
    query: str,
    *,
    model: Any = None,
    scope: str = "unseen",
    limit: int = 5,
    generator_fn: Callable[[str, str], str] | None = None,
    taste_fn: Callable[[list[int]], dict[int, float]] | None = None,
    w_taste: float = 0.0,
    w_comp: float = 0.0,
    exclude_ids: list[int] | None = None,
    rationales: bool = True,
) -> dict:
    """Parse constraints, retrieve under SQL filters, optionally rerank, add grounded rationales.

    ``w_taste`` and ``w_comp`` default to 0 (pure retrieval order) until an eval justifies more.
    ``exclude_ids`` and ``rationales=False`` exist for evaluation (hold-out sets, no text).
    """
    parsed = parse_constraints(query)
    degraded: list[str] = []
    if parsed.filters.get("item_type") == "book":
        degraded.append("books_not_supported: this view recommends films only")

    director_name, director_ids = _director_item_ids(db, query)
    filters = to_search_filters(
        parsed, scope, exclude_ids=exclude_ids, item_ids=director_ids if director_name else None
    )
    if director_name:
        parsed.chips.append(Chip("director", director_name, (0, 0)))

    if model is not None and db.vec_available:
        mode = "rrf"
    else:
        mode = "bm25"
        degraded.append(
            "no_vector: sqlite-vec unavailable" if not db.vec_available
            else "no_model: embedding model not loaded"
        )

    residual = "" if (parsed.intent == "completion" or director_name) else parsed.residual_query
    ranked: list[tuple[int, float]]
    if residual:
        results = search(db, residual, model=model, mode=mode, limit=CANDIDATE_LIMIT,
                         filters=filters, dedupe_items=True)
        top = results[0].score if results and results[0].score else 1.0
        ranked = [(r.item_id, r.score / top) for r in results]
    else:
        cand = _filter_only_candidates(db, filters)
        ranked = [(i, 0.0) for i in cand]

    cand_ids = [i for i, _ in ranked]
    # Gains only matter for ordering when there is no text query or completion is weighted.
    needs_gain = not residual or w_comp > 0
    deltas_all = coll.completion_deltas(db, cand_ids) if needs_gain else {}
    base_by_id = dict(ranked)
    taste: dict[int, float] = {}
    if w_taste > 0 and taste_fn and cand_ids:
        try:
            taste = taste_fn(cand_ids)
        except Exception:
            degraded.append("no_taste: taste ranking unavailable")

    on_list_ids = set(db.get_watchlist_ids())

    def key(entry: tuple[int, float]) -> tuple:
        item_id, base = entry
        gain = coll.best_gain(deltas_all.get(item_id, []))
        score = base + w_taste * taste.get(item_id, 0.0) + w_comp * gain / 100.0
        if residual:
            return (-score,)
        on_list = 1 if item_id in on_list_ids else 0
        if parsed.intent == "completion" or director_name:
            return (-gain, -on_list, -score)
        return (-on_list, -gain, -score)

    ranked.sort(key=key)
    top_ids = [i for i, _ in ranked[:limit]]
    cards = db.get_item_cards(top_ids)
    for item_id, f in item_facts(db, top_ids).items():
        cards[item_id]["genres"] = f["genres"]
    deltas = coll.completion_deltas(db, top_ids, with_remaining=True)
    mention_scope = _mention_scope(db) if rationales else None

    picks = []
    for item_id in top_ids:
        base = base_by_id[item_id]
        gain = coll.best_gain(deltas.get(item_id, []))
        score = base + w_taste * taste.get(item_id, 0.0) + w_comp * gain / 100.0
        score_parts = {
            "retrieval": round(base, 4),
            "taste": round(taste[item_id], 4) if item_id in taste else None,
            "completion_boost": round(w_comp * gain / 100.0, 4),
        }
        card = cards[item_id]
        if not rationales:
            picks.append({
                "item": card, "score": round(score, 4), "score_parts": score_parts,
                "completion": [asdict(d) for d in deltas.get(item_id, [])], "rationale": None,
            })
            continue
        chunks = _item_chunks(db, item_id, residual, model, mode)
        assembled = assemble_context(chunks, token_budget=RATIONALE_TOKEN_BUDGET)
        hearts = {
            d["name"]: _hearts_by_director(db, d["person_id"], item_id) for d in card["directors"]
        }
        facts = _facts(card, deltas.get(item_id, []), hearts)

        text = _template_text(
            card, parsed.filters, deltas.get(item_id, []), hearts, assembled.chunks
        )
        check = check_grounding(db, text, assembled, mention_scope)
        generator = "template"
        if generator_fn is None:
            degraded.append("no_llm: template rationale")
        else:
            facts_block = "\n".join(f"Fact: {f['label']}: {f['value']}" for f in facts)
            try:
                llm_text = generator_fn(query, assembled.context_text + "\n" + facts_block)
                llm_check = check_grounding(db, llm_text, assembled, mention_scope)
                ok = (
                    bool(llm_text.strip()) and llm_check["is_fully_grounded"]
                    and llm_check["citations_valid"]
                    and (not assembled.chunks or "[^" in llm_text)
                )
            except Exception:
                ok = False
            if ok:
                text, check, generator = llm_text, llm_check, "llm"
            else:
                degraded.append("llm_ungrounded: fell back to template rationale")

        meta = _chunk_meta(db, [c.chunk_id for c in assembled.chunks])
        picks.append({
            "item": card,
            "score": round(score, 4),
            "score_parts": score_parts,
            "completion": [asdict(d) for d in deltas.get(item_id, [])],
            "rationale": {
                "text": text,
                "generator": generator,
                "citations": [
                    {
                        "n": c.citation_id, "chunk_id": c.chunk_id, "item_id": c.item_id,
                        "title": c.title, "year": c.year,
                        "section_name": meta.get(c.chunk_id, {}).get("section_name"),
                        "source": meta.get(c.chunk_id, {}).get("source"),
                        "snippet": _snippet(c.text, 240),
                    }
                    for c in assembled.chunks
                ],
                "groundedness": check["groundedness"],
                "facts": facts,
            },
        })

    response = {
        "query": query,
        "parsed": parsed.to_dict(),
        "mode_used": mode,
        "degraded": list(dict.fromkeys(degraded)),
        "excluded_unknown_runtime": _count_unknown_runtime(db, filters),
        "picks": picks,
        "empty": None,
    }
    if not picks:
        response["empty"] = _explain_empty(db, parsed, scope, residual, model, mode, director_ids)
    return response


def _explain_empty(
    db: Database, parsed: ParsedQuery, scope: str, residual: str, model: Any, mode: str,
    director_ids: list[int],
) -> dict:
    """Say which active constraint, if relaxed, would bring results back."""
    base = to_search_filters(parsed, scope, item_ids=director_ids or None)
    groups = {
        "runtime": ("runtime_min", "runtime_max"),
        "decade": ("decade",),
        "years": ("year_min", "year_max"),
        "status": ("seen", "on_watchlist"),
    }
    relax = []
    for name, fields in groups.items():
        if all(getattr(base, f) is None for f in fields):
            continue
        relaxed = SearchFilters(**{**base.__dict__, **{f: None for f in fields}})
        if residual:
            n = len(search(db, residual, model=model, mode=mode, limit=5, filters=relaxed))
        else:
            n = len(_filter_only_candidates(db, relaxed))
        if n:
            relax.append({"filter": name, "would_match": n})
    return {"message": "Nothing in your index matches all of those constraints.", "relax": relax}
