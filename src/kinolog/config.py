"""Central defaults: filesystem locations and default strategy names.

Paths are relative to the working directory, as they always were. This module sits below every
other layer and must not import from the rest of the package.
"""

from __future__ import annotations

from pathlib import Path

DATA_DIR = Path("data")
DEFAULT_DB_PATH = DATA_DIR / "index.db"

CACHE_DIR = DATA_DIR / "cache"
TMDB_CACHE_DIR = CACHE_DIR / "tmdb"
OPENLIBRARY_CACHE_DIR = CACHE_DIR / "openlibrary"
WIKI_CACHE_DIR = CACHE_DIR / "wiki"
WIKIDATA_CACHE_DIR = CACHE_DIR / "wikidata"
SUBS_CACHE_DIR = CACHE_DIR / "subs"

ENV_FILE = Path(".env")
TMDB_API_KEY_VAR = "TMDB_API_KEY"

DEFAULT_MODEL = "bge_m3"
DEFAULT_STRATEGY = "whole"
DEFAULT_RANKER = "nearest_exemplar"


def get_tmdb_api_key() -> str:
    """TMDB API key from the environment, else from ``.env`` in the working directory."""
    import os

    key = os.environ.get(TMDB_API_KEY_VAR, "")
    if not key:
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text().splitlines():
                if line.startswith(f"{TMDB_API_KEY_VAR}="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise ValueError(
            "TMDB_API_KEY not set. Set it as an environment variable or in .env"
        )
    return key
