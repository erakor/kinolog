"""Wikidata and Wikipedia HTTP calls, with an on-disk cache of the raw JSON."""

from __future__ import annotations

import logging
import urllib.parse

from kinolog.config import WIKI_CACHE_DIR, WIKIDATA_CACHE_DIR
from kinolog.sources.http_cache import fetch_json, read_json, write_json

logger = logging.getLogger(__name__)

USER_AGENT = "Kinolog/1.0 (personal-film-index)"


def _fetch_wikidata_sitelinks(wikidata_id: str) -> dict[str, str]:
    """
    Fetch sitelinks for a Wikidata entity (e.g., 'Q18411' -> {'en': 'La Dolce Vita', 'it': '...', 'fr': '...'}).
    Caches raw JSON in data/cache/wikidata/{wikidata_id}.json.
    """
    WIKIDATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = WIKIDATA_CACHE_DIR / f"{wikidata_id}.json"

    if cache_file.exists():
        data = read_json(cache_file)
    else:
        url = f"https://www.wikidata.org/w/api.php?action=wbgetentities&ids={wikidata_id}&props=sitelinks&format=json"
        data = fetch_json(url, USER_AGENT)
        write_json(cache_file, data)

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
        return read_json(cache_file)

    encoded_title = urllib.parse.quote(title.replace(" ", "_"))
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/mobile-sections/{encoded_title}"

    try:
        data = fetch_json(url, USER_AGENT)
        write_json(cache_file, data)
        return data
    except Exception as e:
        logger.warning("Failed to fetch Wikipedia (%s) for '%s': %s", lang, title, e)
        return {}
