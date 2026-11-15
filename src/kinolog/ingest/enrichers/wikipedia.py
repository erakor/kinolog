"""Wikipedia enricher: fetch Wikipedia articles in EN, FR, IT from Wikidata IDs."""

from __future__ import annotations

import json
import logging
import urllib.parse

from kinolog.config import WIKI_CACHE_DIR, WIKIDATA_CACHE_DIR
from kinolog.store import Database

logger = logging.getLogger(__name__)



def _fetch_wikidata_sitelinks(wikidata_id: str) -> dict[str, str]:
    """
    Fetch sitelinks for a Wikidata entity (e.g., 'Q18411' -> {'en': 'La Dolce Vita', 'it': '...', 'fr': '...'}).
    Caches raw JSON in data/cache/wikidata/{wikidata_id}.json.
    """
    WIKIDATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = WIKIDATA_CACHE_DIR / f"{wikidata_id}.json"

    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    else:
        import urllib.request

        url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={wikidata_id}&props=sitelinks&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "Kinolog/1.0 (personal-film-index)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    sitelinks = {}
    entity = data.get("entities", {}).get(wikidata_id, {})
    links = entity.get("sitelinks", {})

    for lang in ("en", "fr", "it"):
        wiki_key = f"{lang}wiki"
        if wiki_key in links:
            sitelinks[lang] = links[wiki_key]["title"]

    return sitelinks


def _fetch_wikipedia_sections(title: str, lang: str = "en") -> dict:
    """
    Fetch Wikipedia mobile-sections for a page title.
    Caches raw JSON in data/cache/wiki/{lang}_{clean_title}.json.
    """
    WIKI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = urllib.parse.quote(title.replace(" ", "_"), safe="")
    cache_file = WIKI_CACHE_DIR / f"{lang}_{safe_name}.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    import urllib.request

    encoded_title = urllib.parse.quote(title.replace(" ", "_"))
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/mobile-sections/{encoded_title}"
    req = urllib.request.Request(url, headers={"User-Agent": "Kinolog/1.0 (personal-film-index)"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
    except Exception as e:
        logger.warning("Failed to fetch Wikipedia (%s) for '%s': %s", lang, title, e)
        return {}


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
