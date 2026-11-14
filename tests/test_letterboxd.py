"""Tests for the Letterboxd loader."""

import csv
import os
import tempfile
from pathlib import Path

import pytest

from src.core.db import Database
from src.ingest.letterboxd import load_letterboxd, compute_first_heart_date


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def export_dir(tmp_path):
    """Create a fake Letterboxd export directory."""
    # watched.csv
    watched = tmp_path / "watched.csv"
    with open(watched, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Name", "Year", "Letterboxd URI"])
        writer.writeheader()
        writer.writerow({"Date": "2024-01-15", "Name": "La Dolce Vita", "Year": "1960",
                         "Letterboxd URI": "https://letterboxd.com/film/la-dolce-vita/"})
        writer.writerow({"Date": "2024-02-01", "Name": "8½", "Year": "1963",
                         "Letterboxd URI": "https://letterboxd.com/film/8-half/"})
        writer.writerow({"Date": "2024-03-10", "Name": "Le Mépris", "Year": "1963",
                         "Letterboxd URI": "https://letterboxd.com/film/contempt/"})

    # watchlist.csv
    watchlist = tmp_path / "watchlist.csv"
    with open(watchlist, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Name", "Year", "Letterboxd URI"])
        writer.writeheader()
        writer.writerow({"Date": "2024-04-01", "Name": "Solaris", "Year": "1972",
                         "Letterboxd URI": "https://letterboxd.com/film/solaris/"})

    # likes/films.csv
    likes_dir = tmp_path / "likes"
    likes_dir.mkdir()
    likes = likes_dir / "films.csv"
    with open(likes, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Name", "Year", "Letterboxd URI"])
        writer.writeheader()
        writer.writerow({"Date": "2024-06-01", "Name": "La Dolce Vita", "Year": "1960",
                         "Letterboxd URI": "https://letterboxd.com/film/la-dolce-vita/"})
        writer.writerow({"Date": "2024-06-15", "Name": "8½", "Year": "1963",
                         "Letterboxd URI": "https://letterboxd.com/film/8-half/"})

    return tmp_path


def test_load_letterboxd(db, export_dir):
    stats = load_letterboxd(db, export_dir)

    assert stats["watched"] == 3
    assert stats["watchlist"] == 1
    assert stats["likes"] == 2
    assert stats["first_heart_date"] == "2024-06-01"

    # Check items
    items = db.get_items(item_type="film")
    assert len(items) == 4  # 3 watched + 1 watchlist (no overlap here)

    # Check user status
    liked_items = db.get_items(liked=True)
    assert len(liked_items) == 2


def test_first_heart_date():
    rows = [
        {"Date": "2024-06-01"},
        {"Date": "2024-05-15"},
        {"Date": "2024-07-01"},
    ]
    assert compute_first_heart_date(rows) == "2024-05-15"


def test_idempotent_load(db, export_dir):
    stats1 = load_letterboxd(db, export_dir)
    stats2 = load_letterboxd(db, export_dir)

    # Should not duplicate items
    items = db.get_items(item_type="film")
    assert len(items) == 4
