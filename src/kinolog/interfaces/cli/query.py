"""CLI handlers for search, stats, filmography and crew-overlap (over ``kinolog.services``)."""

from __future__ import annotations

from kinolog import services
from kinolog.interfaces.cli.output import print_table
from kinolog.store import Database


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
