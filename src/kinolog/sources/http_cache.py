"""Shared plumbing for sources that cache raw JSON responses on disk.

Cache file names and locations are part of the on-disk contract (``data/cache/<source>/``);
changing the layout would orphan a user's existing cache.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_json(url: str, user_agent: str, timeout: float = 15) -> Any:
    """GET a URL with urllib and decode the JSON body."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))
