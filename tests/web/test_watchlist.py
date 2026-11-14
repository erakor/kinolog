import pytest

from src.core.taste import TasteScore
from tests.web.seed import seed


def test_list_default_sorted_by_director_impact(client, db):
    seed(db)
    body = client.get("/api/watchlist").json()
    assert body["total"] == 3 and body["summary"]["count"] == 3
    assert body["summary"]["total_minutes"] == 150 + 80 + 99
    titles = [r["title"] for r in body["items"]]
    # Bob 2/3 -> 3/3 is the biggest push, then Ann 2/5 -> 3/5 (ties by title)
    assert titles[0] == "Glass Orchard"
    first = body["items"][0]
    d = first["completion"][0]
    assert d["name"] == "Bob Bergman" and d["before_pct"] == 66.7 and d["after_pct"] == 100.0
    assert first["genres"] == [] and "botanist" in first["overview"]
    assert body["taste_available"] is False


def test_runtime_filter_and_sorts(client, db):
    seed(db)
    r = client.get("/api/watchlist", params={"runtime_max": 90}).json()
    assert [x["title"] for x in r["items"]] == ["Brief Encounter Again"]
    r = client.get("/api/watchlist", params={"sort": "runtime"}).json()
    assert [x["runtime_min"] for x in r["items"]] == [80, 99, 150]
    r = client.get("/api/watchlist", params={"sort": "year"}).json()
    assert [x["year"] for x in r["items"]] == [2005, 2000, 1990]
    r = client.get("/api/watchlist", params={"q": "bergman"}).json()
    assert [x["title"] for x in r["items"]] == ["Glass Orchard"]


def test_bad_sort_422_and_taste_409_without_vec(client, db):
    seed(db)
    assert client.get("/api/watchlist", params={"sort": "nope"}).status_code == 422
    r = client.get("/api/watchlist", params={"sort": "taste"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "taste_unavailable"


def test_taste_sort_with_stubbed_ranker(client, db, monkeypatch):
    ids = seed(db)
    from src.core import taste
    from src.interfaces.web.state import AppState

    monkeypatch.setattr(AppState, "taste_available", lambda self, db, model_name="bge_m3": True)

    def fake(db_, cands, hearts, **kw):
        order = {ids["Brief Encounter Again"]: 0.9, ids["Glass Orchard"]: 0.5}
        return [TasteScore(i, order[i], method="fake") for i in cands if i in order]

    monkeypatch.setitem(taste.RANKERS, "nearest_exemplar", fake)
    r = client.get("/api/watchlist", params={"sort": "taste"}).json()
    assert [x["title"] for x in r["items"]][:2] == ["Brief Encounter Again", "Glass Orchard"]
    assert r["items"][0]["taste"]["score"] == pytest.approx(0.9)
    assert r["items"][2]["taste"] is None
