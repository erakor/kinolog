"""Tests for the Goodreads loader."""

import csv
import pytest

from kinolog.store import Database
from kinolog.ingest.goodreads import load_goodreads, _clean_isbn


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def goodreads_csv(tmp_path):
    """Create a fake Goodreads export."""
    csv_path = tmp_path / "goodreads_library_export.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "Book Id", "Title", "Author", "ISBN", "ISBN13",
            "My Rating", "Year Published", "Original Publication Year",
            "Date Read", "Date Added", "Bookshelves", "Exclusive Shelf",
        ])
        writer.writeheader()
        writer.writerow({
            "Book Id": "1", "Title": "The Stranger", "Author": "Albert Camus",
            "ISBN": '="0679720200"', "ISBN13": '="9780679720201"',
            "My Rating": "0", "Year Published": "1989",
            "Original Publication Year": "1942",
            "Date Read": "2024-01-01", "Date Added": "2023-12-01",
            "Bookshelves": "", "Exclusive Shelf": "read",
        })
        writer.writerow({
            "Book Id": "2", "Title": "If on a winter's night a traveler",
            "Author": "Italo Calvino",
            "ISBN": '=""', "ISBN13": '="9780156439619"',
            "My Rating": "0", "Year Published": "1981",
            "Original Publication Year": "1979",
            "Date Read": "", "Date Added": "2024-03-01",
            "Bookshelves": "", "Exclusive Shelf": "to-read",
        })
    return csv_path


def test_clean_isbn():
    assert _clean_isbn('="0451524934"') == "0451524934"
    assert _clean_isbn("='0451524934'") == "0451524934"
    assert _clean_isbn('=""') is None
    assert _clean_isbn(None) is None
    assert _clean_isbn("") is None


def test_load_goodreads(db, goodreads_csv):
    stats = load_goodreads(db, goodreads_csv)

    assert stats["total"] == 2
    assert stats["read"] == 1
    assert stats["to_read"] == 1
    assert stats["with_isbn"] == 2  # both have ISBN13

    books = db.get_items(item_type="book")
    assert len(books) == 2

    # Check ISBN was cleaned
    stranger = db.execute("SELECT isbn FROM items WHERE title = 'The Stranger'").fetchone()
    assert stranger["isbn"] == "9780679720201"


def test_idempotent_load(db, goodreads_csv):
    load_goodreads(db, goodreads_csv)
    load_goodreads(db, goodreads_csv)

    books = db.get_items(item_type="book")
    assert len(books) == 2
