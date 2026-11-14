"""Letterboxd CSV loader: watched, watchlist, and likes/films."""

from __future__ import annotations

import csv
import logging
import zipfile
from datetime import date
from pathlib import Path
from typing import Iterator

from src.core.db import Database

logger = logging.getLogger(__name__)

# Expected column sets (Letterboxd exports)
EXPECTED_COLS = {"Date", "Name", "Year", "Letterboxd URI"}
DIARY_EXTRA_COLS = {"Rating", "Rewatch", "Tags"}  # diary.csv has more


def _parse_csv(path: Path) -> list[dict]:
    """Parse a Letterboxd CSV, returning list of row dicts."""
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if rows:
        cols = set(rows[0].keys())
        missing = EXPECTED_COLS - cols
        if missing:
            logger.warning("CSV %s missing expected columns: %s (has: %s)", path.name, missing, cols)
    return rows


def _parse_year(raw: str | None) -> int | None:
    if not raw:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _parse_date(raw: str | None) -> str | None:
    """Parse a date string, return ISO format or None."""
    if not raw or not raw.strip():
        return None
    return raw.strip()


def find_csvs(export_dir: Path) -> dict[str, Path]:
    """Find Letterboxd CSV files. Handles both flat dir and zip."""
    result = {}

    # Check for zip
    zips = list(export_dir.glob("letterboxd-*.zip")) + list(export_dir.glob("*.zip"))
    if zips:
        zip_path = zips[0]
        logger.info("Found Letterboxd zip: %s", zip_path)
        extract_dir = export_dir / "letterboxd"
        if not extract_dir.exists():
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        export_dir = extract_dir

    # Look for CSVs
    for name in ["watched.csv", "watchlist.csv"]:
        p = export_dir / name
        if p.exists():
            result[name.replace(".csv", "")] = p

    # likes can be in likes/films.csv or films.csv
    likes_path = export_dir / "likes" / "films.csv"
    if not likes_path.exists():
        likes_path = export_dir / "films.csv"
    if likes_path.exists():
        result["likes"] = likes_path

    # Also check for diary.csv (richer data)
    diary_path = export_dir / "diary.csv"
    if diary_path.exists():
        result["diary"] = diary_path

    return result


def compute_first_heart_date(likes_rows: list[dict]) -> str | None:
    """Find the earliest like date. Returns ISO date string."""
    dates = []
    for row in likes_rows:
        d = _parse_date(row.get("Date"))
        if d:
            dates.append(d)
    if not dates:
        return None
    return min(dates)


def load_letterboxd(db: Database, export_dir: str | Path) -> dict:
    """
    Load Letterboxd exports into the database.

    Returns stats dict with counts and first_heart_date.
    """
    export_dir = Path(export_dir)
    csvs = find_csvs(export_dir)

    if not csvs:
        raise FileNotFoundError(
            f"No Letterboxd CSVs found in {export_dir}. "
            "Expected watched.csv, watchlist.csv, and/or likes/films.csv"
        )

    logger.info("Found Letterboxd CSVs: %s", list(csvs.keys()))
    stats = {"watched": 0, "watchlist": 0, "likes": 0, "first_heart_date": None}

    # --- Load watched ---
    if "watched" in csvs:
        watched_rows = _parse_csv(csvs["watched"])
        for row in watched_rows:
            title = row.get("Name", "").strip()
            year = _parse_year(row.get("Year"))
            if not title:
                continue
            item_id = db.upsert_item("film", title, year)
            db.upsert_user_status(
                item_id,
                seen=1,
                seen_date=_parse_date(row.get("Date")),
                source="letterboxd",
            )
            stats["watched"] += 1
        logger.info("Loaded %d watched films", stats["watched"])

    # --- Load watchlist ---
    if "watchlist" in csvs:
        watchlist_rows = _parse_csv(csvs["watchlist"])
        for row in watchlist_rows:
            title = row.get("Name", "").strip()
            year = _parse_year(row.get("Year"))
            if not title:
                continue
            item_id = db.upsert_item("film", title, year)
            db.upsert_user_status(
                item_id,
                on_watchlist=1,
                source="letterboxd",
            )
            stats["watchlist"] += 1
        logger.info("Loaded %d watchlist films", stats["watchlist"])

    # --- Load likes ---
    if "likes" in csvs:
        likes_rows = _parse_csv(csvs["likes"])
        first_heart = compute_first_heart_date(likes_rows)
        stats["first_heart_date"] = first_heart
        logger.info("First heart date: %s", first_heart)

        for row in likes_rows:
            title = row.get("Name", "").strip()
            year = _parse_year(row.get("Year"))
            if not title:
                continue
            item_id = db.upsert_item("film", title, year)
            db.upsert_user_status(
                item_id,
                liked=1,
                liked_date=_parse_date(row.get("Date")),
                source="letterboxd",
            )
            stats["likes"] += 1
        logger.info("Loaded %d liked films", stats["likes"])

    # --- Load diary if present (richer watched data with dates) ---
    if "diary" in csvs:
        diary_rows = _parse_csv(csvs["diary"])
        for row in diary_rows:
            title = row.get("Name", "").strip()
            year = _parse_year(row.get("Year"))
            if not title:
                continue
            item_id = db.upsert_item("film", title, year)
            db.upsert_user_status(
                item_id,
                seen=1,
                seen_date=_parse_date(row.get("Date")),
                source="letterboxd",
            )

    db.conn.commit()
    return stats
