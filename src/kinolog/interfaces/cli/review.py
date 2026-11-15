"""CLI to review the match queue — resolve ambiguous TMDB matches."""

from __future__ import annotations

from kinolog.config import DEFAULT_DB_PATH
from kinolog.store import Database


def review_queue(db_path: str = str(DEFAULT_DB_PATH)):
    """Interactive CLI to clear the match review queue."""
    db = Database(db_path)
    queue = db.get_review_queue()

    if not queue:
        print("✅ Review queue is empty!")
        return

    print(f"\n📋 {len(queue)} items to review\n")

    for i, entry in enumerate(queue):
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(queue)}] {entry['title']} ({entry['year']})")
        print(f"  Reason: {entry['reason']}")
        print(f"  Item ID: {entry['item_id']}")

        candidates = entry.get("candidates", [])
        if not candidates:
            print("  No candidates found.")
            response = input("  [s]kip / [r]eject / [q]uit: ").strip().lower()
            if response == "r":
                db.resolve_review(entry["item_id"], reject=True)
                print("  → Rejected")
            elif response == "q":
                break
            continue

        print("  Candidates:")
        for j, c in enumerate(candidates):
            score = c.get("score", 0)
            print(f"    {j+1}. [{score:.2f}] {c['title']} ({c.get('release_date', '?')}) "
                  f"  original: {c.get('original_title', '')}  TMDB: {c['tmdb_id']}")

        response = input(f"  Choose [1-{len(candidates)}] / [s]kip / [r]eject / [q]uit: ").strip().lower()

        if response == "q":
            break
        elif response == "r":
            db.resolve_review(entry["item_id"], reject=True)
            print("  → Rejected")
        elif response == "s":
            print("  → Skipped")
        elif response.isdigit():
            idx = int(response) - 1
            if 0 <= idx < len(candidates):
                tmdb_id = candidates[idx]["tmdb_id"]
                db.resolve_review(entry["item_id"], tmdb_id=tmdb_id)
                print(f"  → Matched to TMDB {tmdb_id}")
            else:
                print("  → Invalid choice, skipped")

    remaining = len(db.get_review_queue())
    print(f"\n{'='*60}")
    print(f"Done. {remaining} items remaining in queue.")
    db.close()


if __name__ == "__main__":
    review_queue()
