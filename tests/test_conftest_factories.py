from tests.conftest import make_document, make_film


def test_make_film_and_document(db):
    i = make_film(db, "Solaris", 1972, runtime_min=167, seen=1, liked=1)
    d = make_document(db, i, "Solaris (1972)\nAn ocean planet.")
    card = db.get_item_card(i)
    assert card["title"] == "Solaris" and card["status"]["seen"] and card["status"]["liked"]
    assert db.get_item_sources(i) == ["tmdb"]
    assert d is not None
