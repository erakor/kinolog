"""TMDB enricher: fetch details and build documents from TMDB data."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.core.db import Database, content_hash
from src.ingest.resolvers.tmdb import TMDBResolver

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/tmdb")

# Key crew roles to extract
KEY_ROLES = {
    "Directing": ["Director"],
    "Writing": ["Writer", "Screenplay", "Story"],
    "Camera": ["Director of Photography"],
    "Sound": ["Original Music Composer", "Music"],
    "Production": ["Producer"],
    "Editing": ["Editor"],
}


def is_tv_movie(genre_names: list[str]) -> bool:
    return any(g.strip().lower() == "tv movie" for g in genre_names)


def backfill_runtime_and_tv(db: Database) -> dict:
    """Set items.runtime_min / is_tv from existing TMDB documents (no network).

    Parses the "Runtime: N minutes" and "Genres: ..." lines written by _build_document_text.
    Items that already have a runtime are left alone.
    """
    stats = {"runtime": 0, "tv": 0, "scanned": 0}
    rows = db.execute(
        """SELECT i.id, i.runtime_min, d.text FROM items i
           JOIN documents d ON d.item_id = i.id AND d.source = 'tmdb'
           GROUP BY i.id"""
    ).fetchall()
    for r in rows:
        stats["scanned"] += 1
        text = r["text"] or ""
        m = re.search(r"^Runtime:\s*(\d+)\s*minutes", text, re.MULTILINE)
        if m and r["runtime_min"] is None:
            db.execute("UPDATE items SET runtime_min = ? WHERE id = ?", (int(m.group(1)), r["id"]))
            stats["runtime"] += 1
        g = re.search(r"^Genres:\s*(.+)$", text, re.MULTILINE)
        if g and is_tv_movie(g.group(1).split(",")):
            db.execute("UPDATE items SET is_tv = 1 WHERE id = ?", (r["id"],))
            stats["tv"] += 1
    db.conn.commit()
    return stats


def imdb_id_from_details(details: dict) -> str | None:
    """IMDb title id (tt...) from TMDB details, top-level field or external_ids."""
    for value in (details.get("imdb_id"), (details.get("external_ids") or {}).get("imdb_id")):
        if isinstance(value, str) and re.fullmatch(r"tt\d{5,}", value.strip()):
            return value.strip()
    return None


def backfill_imdb_ids(db: Database, cache_dir: Path = CACHE_DIR) -> dict:
    """Set items.imdb_id from cached TMDB detail JSON (no network). Existing ids are kept."""
    stats = {"scanned": 0, "imdb_ids": 0}
    rows = db.execute(
        "SELECT id, tmdb_id FROM items WHERE tmdb_id IS NOT NULL AND imdb_id IS NULL"
    ).fetchall()
    for r in rows:
        path = Path(cache_dir) / f"movie_{r['tmdb_id']}.json"
        if not path.exists():
            continue
        stats["scanned"] += 1
        try:
            details = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning("Unreadable TMDB cache %s: %s", path, e)
            continue
        imdb_id = imdb_id_from_details(details)
        if imdb_id:
            db.execute("UPDATE items SET imdb_id = ? WHERE id = ?", (imdb_id, r["id"]))
            stats["imdb_ids"] += 1
    db.conn.commit()
    return stats


def _extract_crew(credits: dict) -> list[dict]:
    """Extract key crew members from TMDB credits."""
    crew = []
    for member in credits.get("crew", []):
        dept = member.get("department", "")
        job = member.get("job", "")
        if dept in KEY_ROLES and job in KEY_ROLES[dept]:
            crew.append({
                "tmdb_person_id": member["id"],
                "name": member["name"],
                "role": job,
                "department": dept,
            })
    return crew


def _extract_cast(credits: dict, limit: int = 10) -> list[dict]:
    """Extract top cast from TMDB credits."""
    cast = []
    for member in credits.get("cast", [])[:limit]:
        cast.append({
            "tmdb_person_id": member["id"],
            "name": member["name"],
            "role": member.get("character", ""),
            "department": "Acting",
        })
    return cast


def _build_document_text(details: dict, lang: str = "en") -> str:
    """Build a searchable document from TMDB details for a given language."""
    parts = []

    # Title
    title = details.get("title", "")
    orig_title = details.get("original_title", "")
    if orig_title and orig_title != title:
        parts.append(f"{title} ({orig_title})")
    else:
        parts.append(title)

    # Year
    release = details.get("release_date", "")
    if release:
        parts.append(f"({release[:4]})")

    # Genres
    genres = [g["name"] for g in details.get("genres", [])]
    if genres:
        parts.append(f"Genres: {', '.join(genres)}")

    # Countries
    countries = [c["name"] for c in details.get("production_countries", [])]
    if countries:
        parts.append(f"Countries: {', '.join(countries)}")

    # Languages
    langs = [la["english_name"] for la in details.get("spoken_languages", [])]
    if langs:
        parts.append(f"Languages: {', '.join(langs)}")

    # Runtime
    runtime = details.get("runtime")
    if runtime:
        parts.append(f"Runtime: {runtime} minutes")

    # Director(s)
    credits = details.get("credits", {})
    directors = [m["name"] for m in credits.get("crew", []) if m.get("job") == "Director"]
    if directors:
        parts.append(f"Directed by: {', '.join(directors)}")

    # Key crew
    dps = [m["name"] for m in credits.get("crew", []) if m.get("job") == "Director of Photography"]
    if dps:
        parts.append(f"Cinematography: {', '.join(dps)}")

    writers = [m["name"] for m in credits.get("crew", [])
               if m.get("job") in ("Writer", "Screenplay")]
    if writers:
        parts.append(f"Written by: {', '.join(writers)}")

    composers = [m["name"] for m in credits.get("crew", [])
                 if m.get("job") in ("Original Music Composer", "Music")]
    if composers:
        parts.append(f"Music: {', '.join(composers)}")

    # Top cast
    cast = credits.get("cast", [])[:8]
    if cast:
        cast_strs = [f"{m['name']} as {m.get('character', '?')}" for m in cast]
        parts.append(f"Cast: {', '.join(cast_strs)}")

    # Keywords
    keywords = [k["name"] for k in details.get("keywords", {}).get("keywords", [])]
    if keywords:
        parts.append(f"Keywords: {', '.join(keywords)}")

    # Overview — use translation if available
    overview = details.get("overview", "")
    if lang != "en":
        translations = details.get("translations", {}).get("translations", [])
        for t in translations:
            if t.get("iso_639_1") == lang:
                translated = t.get("data", {}).get("overview", "")
                if translated:
                    overview = translated
                    break
    if overview:
        parts.append(f"\n{overview}")

    return "\n".join(parts)


def enrich_item(
    db: Database,
    resolver: TMDBResolver,
    item_id: int,
    languages: tuple[str, ...] = ("en", "fr", "it"),
) -> dict:
    """
    Fetch TMDB details for an item, store credits, and build documents.

    Returns stats about what was created/updated.
    """
    item = db.get_item(item_id)
    if not item or not item.get("tmdb_id"):
        return {"status": "skipped", "reason": "no_tmdb_id"}

    tmdb_id = item["tmdb_id"]
    stats = {"tmdb_id": tmdb_id, "credits": 0, "documents": 0}

    # Fetch details (cached on disk)
    try:
        details = resolver.get_details(tmdb_id)
    except Exception as e:
        logger.error("Failed to fetch TMDB details for %d: %s", tmdb_id, e)
        return {"status": "error", "error": str(e)}

    # Update item with original title
    orig_title = details.get("original_title")
    if orig_title and orig_title != item["title"]:
        db.execute(
            "UPDATE items SET original_title = ? WHERE id = ?",
            (orig_title, item_id),
        )

    # Store wikidata ID from external_ids if available
    ext_ids = details.get("external_ids", {})
    wikidata_id = ext_ids.get("wikidata_id")
    if wikidata_id:
        db.execute(
            "UPDATE items SET wikidata_id = ? WHERE id = ? AND wikidata_id IS NULL",
            (wikidata_id, item_id),
        )

    # IMDb id: the key for the OMDb ratings enricher
    imdb_id = imdb_id_from_details(details)
    if imdb_id:
        db.execute("UPDATE items SET imdb_id = ? WHERE id = ?", (imdb_id, item_id))

    # Structured runtime / TV flag (used for filters and collection completion)
    runtime = details.get("runtime")
    if runtime:
        db.execute("UPDATE items SET runtime_min = ? WHERE id = ?", (int(runtime), item_id))
    if is_tv_movie([g.get("name", "") for g in details.get("genres", [])]):
        db.execute("UPDATE items SET is_tv = 1 WHERE id = ?", (item_id,))

    # Register in raw_cache
    cache_path = f"data/cache/tmdb/movie_{tmdb_id}.json"
    db.cache_put("tmdb", str(tmdb_id), cache_path)

    # --- Credits ---
    credits = details.get("credits", {})
    crew = _extract_crew(credits)
    cast = _extract_cast(credits)

    for member in crew + cast:
        person_id = db.upsert_person(member["name"], member["tmdb_person_id"])
        db.upsert_credit(item_id, person_id, member["role"], member["department"])
        stats["credits"] += 1

    # --- Documents (one per language) ---
    for lang in languages:
        text = _build_document_text(details, lang=lang)
        if text.strip():
            db.upsert_document(item_id, source="tmdb", lang=lang, text=text)
            stats["documents"] += 1

    db.conn.commit()
    return stats


def enrich_all(
    db: Database,
    resolver: TMDBResolver,
    item_type: str = "film",
    languages: tuple[str, ...] = ("en", "fr", "it"),
) -> dict:
    """Enrich all resolved items. Returns aggregate stats."""
    items = db.execute(
        """SELECT id, tmdb_id FROM items
           WHERE item_type = ? AND tmdb_id IS NOT NULL
           AND match_status IN ('auto', 'manual')""",
        (item_type,),
    ).fetchall()

    total_stats = {"total": len(items), "enriched": 0, "credits": 0, "documents": 0, "errors": 0}
    logger.info("Enriching %d %ss with TMDB data...", len(items), item_type)

    for i, item in enumerate(items):
        try:
            stats = enrich_item(db, resolver, item["id"], languages=languages)
            if stats.get("status") != "error":
                total_stats["enriched"] += 1
                total_stats["credits"] += stats.get("credits", 0)
                total_stats["documents"] += stats.get("documents", 0)
            else:
                total_stats["errors"] += 1
        except Exception as e:
            logger.error("Error enriching item %d: %s", item["id"], e)
            total_stats["errors"] += 1

        if (i + 1) % 50 == 0:
            logger.info("Enrichment progress: %d/%d", i + 1, len(items))

    logger.info("Enrichment complete: %s", total_stats)
    return total_stats
