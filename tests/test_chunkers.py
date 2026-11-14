"""Tests for chunking strategies."""

import pytest

from src.core.db import Database
from src.core.chunkers import (
    chunk_whole_document,
    chunk_fixed_window,
    chunk_by_section,
    chunk_document,
    STRATEGIES,
)


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


def test_chunk_whole_document():
    text = "This is a test document about a film."
    chunks = chunk_whole_document(text)
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].ord == 0


def test_chunk_fixed_window():
    # Create text that's about 3000 chars (1000 tokens at 3 chars/token)
    text = "word " * 600  # 3000 chars
    chunks = chunk_fixed_window(text, window_tokens=256, overlap_tokens=50)
    assert len(chunks) > 1
    # Check ordering
    for i, chunk in enumerate(chunks):
        assert chunk.ord == i


def test_chunk_by_section():
    text = """La Dolce Vita (1960)
Genres: Drama, Comedy
Countries: Italy, France
Directed by: Federico Fellini

Cast:
Marcello Mastroianni as Marcello Rubini
Anita Ekberg as Sylvia

A film about modern Roman society."""

    chunks = chunk_by_section(text, prepend_title=True)
    assert len(chunks) >= 2
    # Section chunks should have section names
    section_names = [c.section_name for c in chunks if c.section_name]
    assert "Cast" in section_names


def test_chunk_document_in_db(db):
    item_id = db.upsert_item("film", "Test Film", 2000)
    doc_id = db.upsert_document(item_id, "tmdb", "en", "A test document about films and cinema.")

    chunk_ids = chunk_document(db, doc_id, strategy="whole")
    assert len(chunk_ids) == 1

    # Verify chunk was stored
    chunk = db.execute("SELECT * FROM chunks WHERE id = ?", (chunk_ids[0],)).fetchone()
    assert chunk["strategy"] == "whole"
    assert chunk["item_id"] == item_id


def test_strategies_registry():
    assert "whole" in STRATEGIES
    assert "fixed_256_50" in STRATEGIES
    assert "section" in STRATEGIES
