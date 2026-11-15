"""Wikipedia enricher: fetch Wikipedia articles in EN, FR, IT from Wikidata IDs."""

from __future__ import annotations

import logging

from kinolog.sources.wikipedia.client import _fetch_wikidata_sitelinks, _fetch_wikipedia_sections
from kinolog.store import Database

logger = logging.getLogger(__name__)


def _clean_html_text(html: str) -> str:
    """Strip HTML tags and unescape HTML entities without extra dependencies."""
    import html as html_lib
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    # Collapse multiple whitespaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_wikipedia_document(title: str, sections_data: dict, lang: str = "en") -> str:
    """
    Format Wikipedia sections (lead, plot, production, reception) into structured document text.
    """
    parts = [f"Title: {title} (Wikipedia {lang.upper()})"]

    # Lead section
    lead_paras = sections_data.get("lead", {}).get("sections", [])
    for sec in lead_paras:
        clean = _clean_html_text(sec.get("text", ""))
        if clean:
            parts.append(clean)

    # Remaining sections (plot, production, themes, critical reception)
    sections = sections_data.get("remaining", {}).get("sections", [])
    wanted_sections = {
        # EN
        "plot", "synopsis", "premise", "production", "development",
        "filming", "themes", "reception", "critical response", "legacy",
        # FR
        "synopsis", "résumé", "fiche technique", "distribution", "tournage",
        "accueil", "critique", "analyse", "thèmes",
        # IT
        "trama", "produzione", "accoglienza", "critica", "temi",
    }

    for sec in sections:
        line = sec.get("line", "").strip()
        line_lower = line.lower()
        if any(w in line_lower for w in wanted_sections):
            text = _clean_html_text(sec.get("text", ""))
            if text:
                parts.append(f"\n[{line}]\n{text}")

    return "\n\n".join(parts)


def enrich_item_wikipedia(
    db: Database,
    item_id: int,
    languages: tuple[str, ...] = ("en", "fr", "it"),
) -> dict:
    """
    Enrich an item from its wikidata_id by fetching Wikipedia articles in EN, FR, IT.
    """
    item = db.get_item(item_id)
    if not item or not item.get("wikidata_id"):
        return {"status": "skipped", "reason": "no_wikidata_id"}

    wikidata_id = item["wikidata_id"]
    stats = {"item_id": item_id, "wikidata_id": wikidata_id, "documents_added": 0}

    try:
        sitelinks = _fetch_wikidata_sitelinks(wikidata_id)
    except Exception as e:
        logger.warning("Could not fetch sitelinks for %s: %s", wikidata_id, e)
        return {"status": "error", "error": str(e)}

    for lang in languages:
        wiki_title = sitelinks.get(lang)
        if not wiki_title:
            continue

        try:
            sections_data = _fetch_wikipedia_sections(wiki_title, lang=lang)
            if not sections_data:
                continue

            doc_text = build_wikipedia_document(wiki_title, sections_data, lang=lang)
            if len(doc_text.strip()) > 50:
                db.upsert_document(item_id, source="wikipedia", lang=lang, text=doc_text)
                stats["documents_added"] += 1
        except Exception as e:
            logger.warning("Error processing Wikipedia %s '%s': %s", lang, wiki_title, e)

    db.conn.commit()
    return stats
