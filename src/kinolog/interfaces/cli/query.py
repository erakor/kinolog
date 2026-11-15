"""CLI handlers for search, stats, filmography, completion and crew-overlap (over services)."""

from __future__ import annotations

from kinolog import services
from kinolog.interfaces.cli.output import print_table
from kinolog.store import Database, InvalidInputError


def handle_search(
    db_path: str, query: str, mode: str = "bm25", limit: int = 10,
    item_type: str | None = None, seen: bool | None = None,
):
    db = Database(db_path)
    model = None
    if mode in ("vector", "rrf"):
        try:
            from kinolog.index.embedding import BGE_M3
            model = BGE_M3()
        except Exception as e:
            print(f"Vector model not available ({e}), falling back to BM25")
            mode = "bm25"
    results = services.search_items(
        db, query, get_model=lambda: model, mode=mode, limit=limit,
        item_type=item_type, seen=seen,
    )
    rows = [[str(i + 1), r["title"], str(r["year"] or ""), f"{r['score']:.4f}", r["source"]]
            for i, r in enumerate(results)]
    print_table(f"Search: {query} ({mode})", ["#", "Title", "Year", "Score", "Source"], rows)
    db.close()


def handle_stats(db_path: str):
    db = Database(db_path)
    rows = [[k, str(v)] for k, v in services.stats(db).items()]
    print_table("Database Stats", ["Table", "Rows"], rows)
    db.close()


def handle_filmography(db_path: str, name: str, role: str | None = None):
    db = Database(db_path)
    for entry in services.filmography(db, name, role=role):
        print(f"\n{entry['person']} — {entry['role']}")
        print(f"  Seen {entry['seen']}/{entry['total']} in database")
        rows = [[str(f.get("year", "")), f["title"], "✓" if f["seen"] else ""]
                for f in entry["films"]]
        print_table(f"Filmography: {entry['person']}", ["Year", "Title", "Seen"], rows)
    db.close()


def handle_crew_overlap(db_path: str, role: str = "Director", min_overlap: int = 2):
    db = Database(db_path)
    rows = []
    for r in services.crew_overlap(db, role=role, min_overlap=min_overlap):
        films_str = ", ".join(r["films"][:5])
        if len(r["films"]) > 5:
            films_str += f" (+{len(r['films']) - 5})"
        rows.append([r["person"], str(r["heart_count"]), str(r["seen_count"]), films_str])
    print_table(
        f"Crew Overlap — {role}s in hearted films", ["Name", "Hearts", "Seen", "Films"], rows
    )
    db.close()


def handle_completion(
    db_path: str,
    name: str | None = None,
    min_seen: int | None = None,
    min_total: int | None = None,
    limit: int = 25,
):
    db = Database(db_path)
    try:
        results = services.filmography_completion(
            db, name=name, min_seen=min_seen, min_total=min_total, limit=limit
        )
    except InvalidInputError as e:
        print(e)
        db.close()
        return
    if name:
        for r in results:
            rows = []
            for f in r["films"]:
                w = f["if_watched"]
                rows.append([
                    str(f["year"] or ""), f["title"],
                    f"{f['runtime']} min" if f["runtime"] else "?",
                    "✓" if f["seen"] else "", "✓" if f["on_watchlist"] else "",
                    f"{w['before_pct']}% -> {w['after_pct']}%" if w else "",
                ])
            print_table(
                f"{r['person']}: {r['seen']}/{r['total']} ({r['percent']}%, {r['coverage']})",
                ["Year", "Title", "Runtime", "Seen", "WL", "If watched"], rows,
            )
    else:
        rows = [[r["person"], str(r["seen"]), str(r["total"]), f"{r['percent']}%", r["coverage"]]
                for r in results]
        print_table("Director completion", ["Director", "Seen", "Total", "%", "Coverage"], rows)
    if any(r["coverage"] == "index_only" for r in results):
        print("Some totals come from your index only and may be low. "
              "Run `ingest filmographies` to fetch full filmographies.")
    db.close()


def handle_watchlist_impact(
    db_path: str,
    max_runtime: int | None = None,
    include_unseen: bool = False,
    include_unknown_runtime: bool = False,
    limit: int = 20,
):
    db = Database(db_path)
    try:
        results = services.watchlist_director_impact(
            db, max_runtime=max_runtime, include_unseen=include_unseen,
            include_unknown_runtime=include_unknown_runtime, limit=limit,
        )
    except InvalidInputError as e:
        print(e)
        db.close()
        return
    rows = [
        [
            r["title"], str(r["year"] or ""), f"{r['runtime']} min" if r["runtime"] else "?",
            ", ".join(d["person"] for d in r["directors"]),
            "; ".join(f"{d['before']} -> {d['after']}" for d in r["directors"]),
            f"{r['impact']:.3f}",
        ]
        for r in results
    ]
    print_table(
        "Watchlist by director impact",
        ["Title", "Year", "Runtime", "Director(s)", "Before -> After", "Impact"], rows,
    )
    db.close()
