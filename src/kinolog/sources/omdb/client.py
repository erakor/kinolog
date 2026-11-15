"""OMDb HTTP client: lookup by IMDb id, disk-cached and throttled.

Only definitive answers (a hit or "not found") are cached under ``data/cache/omdb/``."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import httpx

from kinolog.config import OMDB_CACHE_DIR, get_api_key

OMDB_BASE = "https://www.omdbapi.com/"
CACHE_DIR = OMDB_CACHE_DIR
PROVIDER = "omdb"
DAILY_LIMIT = 1000


class OMDbQuotaError(RuntimeError):
    """Daily request limit reached, or the key is invalid/inactive: stop the batch."""


class OMDbUnavailableError(RuntimeError):
    """Transport failure or server error (5xx / non-JSON); repeated ones stop the batch."""


# Consecutive OMDbUnavailableErrors after which a batch stops making requests.
MAX_CONSECUTIVE_FAILURES = 3


class OMDbClient:
    """Minimal OMDb client: lookup by IMDb id, disk-cached, throttled."""

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit: float = 0.1,
        cache_dir: Path = CACHE_DIR,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key or get_api_key("OMDB_API_KEY")
        # httpx logs each request URL at INFO, and OMDb takes the key as a query parameter.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self.rate_limit = rate_limit
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.requests_made = 0
        self._last_request = 0.0
        self.client = httpx.Client(base_url=OMDB_BASE, timeout=30.0, transport=transport)

    def cache_path(self, imdb_id: str) -> Path:
        return self.cache_dir / f"{imdb_id}.json"

    def is_cached(self, imdb_id: str) -> bool:
        return self.cache_path(imdb_id).exists()

    def _throttle(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request = time.time()

    def get_by_imdb_id(self, imdb_id: str, refresh: bool = False) -> dict:
        """OMDb title response for an IMDb id (cached unless ``refresh``)."""
        path = self.cache_path(imdb_id)
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))

        self._throttle()
        self.requests_made += 1
        try:
            resp = self.client.get("", params={"i": imdb_id, "apikey": self.api_key})
        except httpx.HTTPError as e:
            # Don't log str(e) for a request error: the URL in it carries the API key.
            raise OMDbUnavailableError(
                f"OMDb request failed for {imdb_id}: {type(e).__name__}"
            ) from None
        try:
            data = resp.json()
        except ValueError:
            raise OMDbUnavailableError(
                f"OMDb returned HTTP {resp.status_code} for {imdb_id}"
            ) from None
        if resp.status_code >= 500:
            raise OMDbUnavailableError(f"OMDb returned HTTP {resp.status_code} for {imdb_id}")

        if data.get("Response") != "True":
            error = str(data.get("Error", ""))
            lowered = error.lower()
            if "limit" in lowered or "api key" in lowered or resp.status_code == 401:
                raise OMDbQuotaError(error or f"HTTP {resp.status_code}")
            if "not found" not in lowered and "incorrect imdb id" not in lowered:
                raise RuntimeError(f"OMDb error for {imdb_id}: {error or resp.status_code}")
            # Definitive "no such title": cache it so it is not re-requested every run.
        elif resp.status_code >= 400:
            raise RuntimeError(f"OMDb returned HTTP {resp.status_code} for {imdb_id}")

        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def close(self):
        self.client.close()
