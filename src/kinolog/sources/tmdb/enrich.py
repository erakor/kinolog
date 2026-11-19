"""TMDB enricher: fetch details and build documents from TMDB data."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from kinolog.config import TMDB_CACHE_DIR
from kinolog.sources.http_cache import read_json
from kinolog.sources.tmdb.client import TMDBClient, tmdb_cache_path
from kinolog.store import Database

logger = logging.getLogger(__name__)

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
            db.set_item_facts(r["id"], runtime_min=int(m.group(1)), commit=False)
            stats["runtime"] += 1
        g = re.search(r"^Genres:\s*(.+)$", text, re.MULTILINE)
        if g and is_tv_movie(g.group(1).split(",")):
            db.set_item_facts(r["id"], is_tv=True, commit=False)
            stats["tv"] += 1
    db.conn.commit()
    return stats


def imdb_id_from_details(details: dict) -> str | None:
    """IMDb title id (tt...) from TMDB details, top-level field or external_ids."""
    for value in (details.get("imdb_id"), (details.get("external_ids") or {}).get("imdb_id")):
        if isinstance(value, str) and re.fullmatch(r"tt\d{5,}", value.strip()):
            return value.strip()
    return None


def apply_details_columns(
    db: Database,
    item_id: int,
    details: dict,
    overwrite: bool = True,
) -> None:
    """Write the structured item columns TMDB details provide (no commit for batched facts).

    Shared by enrichment and the offline cache backfill so a new TMDB-derived column
    is added in one place. With ``overwrite=False`` only empty columns are filled.
    """
    wikidata_id = (details.get("external_ids") or {}).get("wikidata_id")
    if wikidata_id:
        # wikidata_id is UNIQUE: the store skips it if another item already holds it.
        db.set_wikidata_id_if_missing(item_id, wikidata_id)
    # imdb_id is the key for the OMDb ratings enricher; runtime/TV drive filters and collections.
    runtime = details.get("runtime")
    db.set_item_facts(
        item_id,
        imdb_id=imdb_id_from_details(details),
        runtime_min=int(runtime) if runtime else None,
        only_if_empty=not overwrite,
        commit=False,
    )
    if is_tv_movie([g.get("name", "") for g in details.get("genres", [])]):
        db.set_item_facts(item_id, is_tv=True, commit=False)


def backfill_imdb_ids(db: Database, cache_dir: Path = TMDB_CACHE_DIR) -> dict:
    """Fill empty TMDB-derived columns from cached details for items lacking an IMDb id.

    No network; existing values (runtime, ids) are never overwritten.
    """
    stats = {"scanned": 0, "imdb_ids": 0}
    rows = db.execute(
        "SELECT id, tmdb_id FROM items WHERE tmdb_id IS NOT NULL AND imdb_id IS NULL"
    ).fetchall()
    for r in rows:
        path = tmdb_cache_path(r["tmdb_id"], cache_dir)
        if not path.exists():
            continue
        stats["scanned"] += 1
        try:
            details = read_json(path)
        except (OSError, ValueError) as e:
            logger.warning("Unreadable TMDB cache %s: %s", path, e)
            continue
        apply_details_columns(db, r["id"], details, overwrite=False)
        stats["imdb_ids"] += imdb_id_from_details(details) is not None
    db.conn.commit()
    return stats


def _extract_crew(credits: dict) -> list[dict]:
    """Extract key crew members from TMDB credits."""
    crew = []
    for member in credits.get("crew", []):
        dept = member.get("department", "")
        job = member.get("job", "")
        if dept in KEY_ROLES and job in KEY_ROLES[dept]:
            crew.append(
                {
                    "tmdb_person_id": member["id"],
                    "name": member["name"],
                    "role": job,
                    "department": dept,
                }
            )
    return crew


def _extract_cast(credits: dict, limit: int = 10) -> list[dict]:
    """Extract top cast from TMDB credits."""
    cast = []
    for member in credits.get("cast", [])[:limit]:
        cast.append(
            {
                "tmdb_person_id": member["id"],
                "name": member["name"],
                "role": member.get("character", ""),
                "department": "Acting",
            }
        )
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

    writers = [
        m["name"] for m in credits.get("crew", []) if m.get("job") in ("Writer", "Screenplay")
    ]
    if writers:
        parts.append(f"Written by: {', '.join(writers)}")

    composers = [
        m["name"]
        for m in credits.get("crew", [])
        if m.get("job") in ("Original Music Composer", "Music")
    ]
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
    client: TMDBClient,
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
        details = client.get_details(tmdb_id)
    except Exception as e:
        logger.error("Failed to fetch TMDB details for %d: %s", tmdb_id, e)
        return {"status": "error", "error": str(e)}

    # Update item with original title
    orig_title = details.get("original_title")
    if orig_title and orig_title != item["title"]:
        db.set_item_facts(item_id, original_title=orig_title)

    apply_details_columns(db, item_id, details)

    # Register in raw_cache
    db.cache_put("tmdb", str(tmdb_id), tmdb_cache_path(tmdb_id).as_posix())

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
    client: TMDBClient,
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
            stats = enrich_item(db, client, item["id"], languages=languages)
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
