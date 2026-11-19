"""TMDB resolver: match items to TMDB movies (the matching logic; HTTP lives in the client)."""

from __future__ import annotations

import logging

from kinolog.sources.tmdb.client import TMDBClient
from kinolog.store import Database

logger = logging.getLogger(__name__)


class TMDBResolver:
    """Resolve film titles to TMDB IDs."""

    def __init__(self, client: TMDBClient | None = None):
        self.client = client or TMDBClient()

    def _score_candidate(
        self,
        candidate: dict,
        title: str,
        year: int | None,
    ) -> tuple[float, str]:
        """Score a TMDB search result. Returns (score, reason)."""
        c_title = candidate.get("title", "")
        c_orig = candidate.get("original_title", "")
        c_year_str = (candidate.get("release_date") or "")[:4]
        c_year = int(c_year_str) if c_year_str.isdigit() else None

        score = 0.0
        reasons = []

        # Title match
        t_lower = title.lower().strip()
        if c_title.lower().strip() == t_lower or c_orig.lower().strip() == t_lower:
            score += 0.5
            reasons.append("exact_title")
        elif t_lower in c_title.lower() or t_lower in c_orig.lower():
            score += 0.3
            reasons.append("partial_title")

        # Year match
        if year and c_year:
            diff = abs(year - c_year)
            if diff == 0:
                score += 0.4
                reasons.append("exact_year")
            elif diff == 1:
                score += 0.2
                reasons.append("year_drift_1")
            elif diff == 2:
                score += 0.1
                reasons.append("year_drift_2")
            else:
                score -= 0.2
                reasons.append("year_mismatch")
        elif year is None:
            score += 0.1  # small bonus for no year constraint
            reasons.append("no_year_given")

        # Popularity as tiebreaker
        pop = candidate.get("popularity", 0)
        score += min(pop / 1000, 0.1)

        return score, "+".join(reasons)

    def resolve_item(
        self,
        db: Database,
        item_id: int,
        title: str,
        year: int | None,
    ) -> dict | None:
        """
        Try to resolve a film to a TMDB ID.

        Returns the best candidate dict or None.
        Sets match_status on the item: 'auto' if confident, 'queued' if ambiguous.
        """
        # Already resolved?
        item = db.get_item(item_id)
        if item and item.get("tmdb_id"):
            return None

        # Search in EN, then FR, then IT
        all_candidates = []
        seen_ids = set()

        for lang in ["en-US", "fr-FR", "it-IT"]:
            results = self.client.search(title, year=year, language=lang)
            for r in results:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    all_candidates.append(r)

            # Also try without year if we got no results
            if not results and year:
                results = self.client.search(title, year=None, language=lang)
                for r in results:
                    if r["id"] not in seen_ids:
                        seen_ids.add(r["id"])
                        all_candidates.append(r)

        if not all_candidates:
            db.queue_for_review(item_id, [], "no_results")
            db.mark_queued(item_id)
            return None

        # Score candidates
        scored = []
        for c in all_candidates:
            score, reason = self._score_candidate(c, title, year)
            scored.append((score, reason, c))
        scored.sort(key=lambda x: x[0], reverse=True)

        best_score, best_reason, best = scored[0]

        # Also check alternative titles for the top candidate
        if best_score < 0.7 and len(scored) > 0:
            try:
                details = self.client.get_details(best["id"])
                alt_titles = [
                    a["title"] for a in details.get("alternative_titles", {}).get("titles", [])
                ]
                for alt in alt_titles:
                    if alt.lower().strip() == title.lower().strip():
                        best_score += 0.3
                        best_reason += "+alt_title_match"
                        break
            except Exception as e:
                logger.warning("Failed to fetch alt titles for %d: %s", best["id"], e)

        # Decision
        if best_score >= 0.7 and (len(scored) == 1 or scored[0][0] - scored[1][0] > 0.2):
            # Auto-accept
            db.set_match(item_id, tmdb_id=best["id"], confidence=best_score)
            logger.debug(
                "Auto-matched '%s' (%s) -> TMDB %d (%.2f: %s)",
                title,
                year,
                best["id"],
                best_score,
                best_reason,
            )
            return best
        else:
            # Queue for manual review
            candidates_for_review = [
                {
                    "tmdb_id": c["id"],
                    "title": c.get("title"),
                    "original_title": c.get("original_title"),
                    "release_date": c.get("release_date"),
                    "score": s,
                    "reason": r,
                }
                for s, r, c in scored[:5]
            ]
            db.queue_for_review(item_id, candidates_for_review, "ambiguous")
            db.mark_queued(item_id)
            logger.info(
                "Queued '%s' (%s) for review: %d candidates, best=%.2f",
                title,
                year,
                len(candidates_for_review),
                best_score,
            )
            return None

    def resolve_all(self, db: Database, item_type: str = "film") -> dict:
        """Resolve all unresolved items of a given type. Returns stats."""
        items = db.execute(
            "SELECT id, title, year FROM items WHERE item_type = ? AND tmdb_id IS NULL AND match_status IS NULL",
            (item_type,),
        ).fetchall()

        stats = {"total": len(items), "auto": 0, "queued": 0, "errors": 0}
        logger.info("Resolving %d unmatched %ss...", len(items), item_type)

        for i, item in enumerate(items):
            try:
                result = self.resolve_item(db, item["id"], item["title"], item["year"])
                if result:
                    stats["auto"] += 1
                else:
                    stats["queued"] += 1
            except Exception as e:
                logger.error("Error resolving '%s' (%s): %s", item["title"], item["year"], e)
                stats["errors"] += 1

            if (i + 1) % 50 == 0:
                logger.info("Progress: %d/%d", i + 1, len(items))

        logger.info("Resolution complete: %s", stats)
        return stats

    def close(self):
        self.client.close()
