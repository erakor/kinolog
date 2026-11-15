"""Letterboxd CSV loader: watched, watchlist, and likes/films."""

from __future__ import annotations

import csv
import logging
import zipfile
from pathlib import Path

from kinolog.store import Database

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


def _parse_rating(raw: str | None) -> int | None:
    """Letterboxd star rating (0.5-5) to half-star integer 1..10."""
    if not raw or not raw.strip():
        return None
    try:
        value = round(float(raw.strip()) * 2)
    except ValueError:
        return None
    return value if 1 <= value <= 10 else None


def _parse_date(raw: str | None) -> str | None:
    """Parse a date string, return ISO format or None."""
    if not raw or not raw.strip():
        return None
    return raw.strip()


def _has_live_log(db: Database, item_id: int) -> bool:
    row = db.execute(
        "SELECT 1 FROM watch_log WHERE item_id = ? AND deleted_at IS NULL LIMIT 1", (item_id,)
    ).fetchone()
    return row is not None


def _status(db: Database, item_id: int):
    return db.execute("SELECT * FROM user_status WHERE item_id = ?", (item_id,)).fetchone()


def _manual_wins(status, row_date: str | None) -> bool:
    """True if a UI edit is at least as recent as the export row (day granularity)."""
    manual = status["manual_updated_at"] if status else None
    return bool(manual) and (not row_date or manual[:10] >= row_date)


def _source_field(status) -> dict:
    """Only stamp source when unset, so manual provenance is not overwritten."""
    return {} if status and status["source"] else {"source": "letterboxd"}


def _has_tombstone_only(db: Database, item_id: int) -> bool:
    """User deleted every logged viewing of this item."""
    dead = db.execute(
        "SELECT 1 FROM watch_log WHERE item_id = ? AND deleted_at IS NOT NULL LIMIT 1", (item_id,)
    ).fetchone()
    return dead is not None and not _has_live_log(db, item_id)


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Extract a zip, refusing absolute paths and path traversal."""
    root = dest.resolve()
    for name in zf.namelist():
        target = (dest / name).resolve()
        if name.startswith(("/", "\\")) or not target.is_relative_to(root):
            raise ValueError(f"Unsafe path in zip: {name!r}")
    zf.extractall(dest)


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
                _safe_extract(zf, extract_dir)
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

    # Also check for diary.csv (richer data) and ratings.csv
    for name in ("diary", "ratings"):
        p = export_dir / f"{name}.csv"
        if p.exists():
            result[name] = p

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
    stats = {
        "watched": 0, "watchlist": 0, "likes": 0, "diary": 0, "ratings": 0,
        "skipped_manual_override": 0, "first_heart_date": None,
    }

    # --- Load watched ---
    if "watched" in csvs:
        watched_rows = _parse_csv(csvs["watched"])
        for row in watched_rows:
            title = row.get("Name", "").strip()
            year = _parse_year(row.get("Year"))
            if not title:
                continue
            item_id = db.upsert_item("film", title, year)
            if _has_tombstone_only(db, item_id):
                stats["skipped_manual_override"] += 1
                continue
            fields: dict = {"seen": 1, **_source_field(_status(db, item_id))}
            if not _has_live_log(db, item_id):
                fields["seen_date"] = _parse_date(row.get("Date"))
            db.upsert_user_status(item_id, **fields)
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
            added = _parse_date(row.get("Date"))
            st = _status(db, item_id)
            removed = st["watchlist_removed_at"] if st else None
            if removed and (not added or removed[:10] >= added):
                # dequeued in the UI more recently than Letterboxd added it
                stats["skipped_manual_override"] += 1
                continue
            db.set_watchlist(item_id, True, at=added, manual=False)
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
            st = _status(db, item_id)
            liked_on = _parse_date(row.get("Date"))
            if _manual_wins(st, liked_on):
                stats["skipped_manual_override"] += 1
                continue
            db.upsert_user_status(
                item_id, liked=1, liked_date=liked_on, **_source_field(st)
            )
            stats["likes"] += 1
        logger.info("Loaded %d liked films", stats["likes"])

    # --- Load diary (one watch_log entry per viewing) ---
    if "diary" in csvs:
        touched: set[int] = set()
        for row in _parse_csv(csvs["diary"]):
            title = row.get("Name", "").strip()
            year = _parse_year(row.get("Year"))
            if not title:
                continue
            watched_on = _parse_date(row.get("Watched Date")) or _parse_date(row.get("Date"))
            if not watched_on:
                continue
            item_id = db.upsert_item("film", title, year)
            uri = (row.get("Letterboxd URI") or title).strip()
            db.log_watch(
                item_id,
                watched_on,
                rating=_parse_rating(row.get("Rating")),
                rewatch=(row.get("Rewatch") or "").strip().lower() in ("yes", "true", "1"),
                source="letterboxd",
                source_key=f"{uri}|{watched_on}",
            )
            touched.add(item_id)
            stats["diary"] += 1
        for item_id in touched:
            db.recompute_user_status(item_id)
        logger.info("Loaded %d diary entries", stats["diary"])

    # --- Load ratings (current rating per film) ---
    if "ratings" in csvs:
        for row in _parse_csv(csvs["ratings"]):
            title = row.get("Name", "").strip()
            rating = _parse_rating(row.get("Rating"))
            if not title or rating is None:
                continue
            item_id = db.upsert_item("film", title, _parse_year(row.get("Year")))
            if _manual_wins(_status(db, item_id), _parse_date(row.get("Date"))):
                stats["skipped_manual_override"] += 1
                continue
            db.upsert_user_status(item_id, rating=rating)
            stats["ratings"] += 1

    db.conn.commit()
    return stats
