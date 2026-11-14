"""Tests for crew queries."""

import pytest
from src.core.db import Database
from src.core.crew import filmography, crew_overlap_with_hearts, directors_by_heart_count


@pytest.fixture
def db_with_crew():
    db = Database(":memory:")

    # Add items
    id1 = db.upsert_item("film", "La Dolce Vita", 1960)
    id2 = db.upsert_item("film", "8½", 1963)
    id3 = db.upsert_item("film", "Amarcord", 1973)
    id4 = db.upsert_item("film", "Le Mépris", 1963)

    # Status: id1 and id2 are seen & liked; id3 is seen only; id4 is unseen
    db.upsert_user_status(id1, seen=1, liked=1)
    db.upsert_user_status(id2, seen=1, liked=1)
    db.upsert_user_status(id3, seen=1, liked=0)
    db.upsert_user_status(id4, seen=0, liked=0)

    # People
    fellini = db.upsert_person("Federico Fellini", tmdb_person_id=4415)
    godard = db.upsert_person("Jean-Luc Godard", tmdb_person_id=3776)
    mastroianni = db.upsert_person("Marcello Mastroianni", tmdb_person_id=2038)
    rota = db.upsert_person("Nino Rota", tmdb_person_id=1054)

    # Credits
    db.upsert_credit(id1, fellini, "Director", "Directing")
    db.upsert_credit(id2, fellini, "Director", "Directing")
    db.upsert_credit(id3, fellini, "Director", "Directing")
    db.upsert_credit(id4, godard, "Director", "Directing")

    db.upsert_credit(id1, mastroianni, "Marcello Rubini", "Acting")
    db.upsert_credit(id2, mastroianni, "Guido Anselmi", "Acting")

    db.upsert_credit(id1, rota, "Original Music Composer", "Sound")
    db.upsert_credit(id2, rota, "Original Music Composer", "Sound")
    db.upsert_credit(id3, rota, "Original Music Composer", "Sound")

    yield db
    db.close()


def test_filmography(db_with_crew):
    entries = filmography(db_with_crew, person_name="Fellini", role="Director")
    assert len(entries) == 1
    f = entries[0]
    assert f.person_name == "Federico Fellini"
    assert f.total_in_db == 3
    assert f.total_seen == 3
    assert len(f.films) == 3


def test_filmography_unseen(db_with_crew):
    entries = filmography(db_with_crew, person_name="Godard")
    assert len(entries) == 1
    f = entries[0]
    assert f.total_in_db == 1
    assert f.total_seen == 0


def test_crew_overlap_with_hearts(db_with_crew):
    # Fellini (2 liked), Rota (2 liked), Mastroianni (2 liked)
    overlaps = crew_overlap_with_hearts(db_with_crew, role="Director", min_overlap=2)
    assert len(overlaps) == 1
    assert overlaps[0].person_name == "Federico Fellini"
    assert overlaps[0].overlap_count == 2


def test_directors_by_heart_count(db_with_crew):
    directors = directors_by_heart_count(db_with_crew)
    assert len(directors) >= 1
    top = directors[0]
    assert top["name"] == "Federico Fellini"
    assert top["heart_count"] == 2
