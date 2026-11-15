"""Named write methods that replaced ad hoc UPDATE statements in the sources."""

import pytest

from kinolog.store import Database


@pytest.fixture
def db():
    return Database(":memory:")


def test_set_match_tmdb(db):
    i = db.upsert_item("film", "A", 2000)
    db.set_match(i, tmdb_id=7, confidence=0.9)
    item = db.get_item(i)
    assert (item["tmdb_id"], item["match_status"], item["match_confidence"]) == (7, "auto", 0.9)


def test_set_match_openlibrary(db):
    i = db.upsert_item("book", "B", None)
    db.set_match(i, openlibrary_id="/works/OL1W", confidence=0.85)
    item = db.get_item(i)
    assert item["openlibrary_id"] == "/works/OL1W" and item["match_status"] == "auto"
    assert item["tmdb_id"] is None


def test_mark_queued(db):
    i = db.upsert_item("film", "A", 2000)
    db.mark_queued(i)
    assert db.get_item(i)["match_status"] == "queued"


def test_set_item_facts_only_touches_given_fields(db):
    i = db.upsert_item("film", "A", 2000, runtime_min=90)
    db.set_item_facts(i, is_tv=True)
    item = db.get_item(i)
    assert item["is_tv"] == 1 and item["runtime_min"] == 90
    db.set_item_facts(i, runtime_min=75, original_title="Alpha")
    item = db.get_item(i)
    assert (item["runtime_min"], item["original_title"], item["is_tv"]) == (75, "Alpha", 1)


def test_set_item_facts_without_fields_is_a_noop(db):
    i = db.upsert_item("film", "A", 2000)
    db.set_item_facts(i)
    assert db.get_item(i)["title"] == "A"


def test_set_item_facts_commit_false_defers_the_commit(db):
    i = db.upsert_item("film", "A", 2000)
    db.set_item_facts(i, runtime_min=80, commit=False)
    assert db.conn.in_transaction
    db.conn.commit()
    assert db.get_item(i)["runtime_min"] == 80


def test_wikidata_id_is_only_set_when_missing(db):
    i = db.upsert_item("film", "A", 2000)
    db.set_wikidata_id_if_missing(i, "Q1")
    db.set_wikidata_id_if_missing(i, "Q2")
    assert db.get_item(i)["wikidata_id"] == "Q1"


def test_upsert_embedding_stores_a_vector(db):
    if not db.vec_available:
        pytest.skip("sqlite-vec not available")
    import numpy as np

    db.try_create_vec_table("test_model", 4)
    i = db.upsert_item("film", "A", 2000)
    doc = db.upsert_document(i, "tmdb", "en", "text")
    cid = db.upsert_chunk(item_id=i, document_id=doc, strategy="whole", ord=0, text="text")
    db.upsert_embedding("test_model", cid, np.ones(4, dtype=np.float32).tobytes())
    rows = db.execute("SELECT chunk_id, embedding FROM vec_test_model").fetchall()
    assert [r["chunk_id"] for r in rows] == [cid]
    assert np.frombuffer(rows[0]["embedding"], dtype=np.float32).sum() == 4
