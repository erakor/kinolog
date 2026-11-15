import pytest

from kinolog.taste import TasteScore
from tests.interfaces.web.seed import seed


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
    from kinolog import taste
    from kinolog.taste import scores as taste_scores_module

    monkeypatch.setattr(taste, "taste_available", lambda db, model_name="bge_m3": True)
    # taste_scores looks the check up in its own module, the web state through the package
    monkeypatch.setattr(taste_scores_module, "taste_available", lambda db, model_name="bge_m3": True)

    def fake(db_, cands, hearts, **kw):
        order = {ids["Brief Encounter Again"]: 0.9, ids["Glass Orchard"]: 0.5}
        return [TasteScore(i, order[i], method="fake") for i in cands if i in order]

    monkeypatch.setitem(taste.RANKERS, "nearest_exemplar", fake)
    r = client.get("/api/watchlist", params={"sort": "taste"}).json()
    assert [x["title"] for x in r["items"]][:2] == ["Brief Encounter Again", "Glass Orchard"]
    assert r["items"][0]["taste"]["score"] == pytest.approx(0.9)
    assert r["items"][2]["taste"] is None


def test_add_and_remove(client, db):
    ids = seed(db)
    mid = ids["Midnight Ferry"]
    r = client.post("/api/watchlist", json={"item_id": mid})
    assert r.status_code == 200 and r.json()["status"]["on_watchlist"] is True
    assert client.get("/api/watchlist").json()["total"] == 4
    r = client.delete(f"/api/watchlist/{mid}")
    assert r.json()["status"]["on_watchlist"] is False
    assert client.get("/api/watchlist").json()["total"] == 3
    # removal is a record, not a row delete
    assert db.get_item(mid) is not None


def test_unknown_item_404_and_bad_body_422(client, db):
    seed(db)
    assert client.post("/api/watchlist", json={"item_id": 9999}).status_code == 404
    assert client.delete("/api/watchlist/9999").status_code == 404
    assert client.post("/api/watchlist", json={}).status_code == 422


def test_log_as_watched_creates_entry_and_dequeues(client, db):
    ids = seed(db)
    tid = ids["The Long Corridor"]
    r = client.post(
        f"/api/watchlist/{tid}/watched",
        json={"watched_on": "2024-08-01", "rating": 9, "liked": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["entry"]["watched_on"] == "2024-08-01" and body["entry"]["rating"] == 9
    assert body["item"]["status"]["seen"] and not body["item"]["status"]["on_watchlist"]
    assert body["item"]["status"]["liked"]
    assert client.get("/api/watchlist").json()["total"] == 2
    # completion deltas update: Ann now 3/5
    d = client.get("/api/collections/directors", params={"q": "ann"}).json()["items"][0]
    assert d["seen"] == 3


def test_log_as_watched_keep_and_validation(client, db):
    ids = seed(db)
    tid = ids["The Long Corridor"]
    r = client.post(f"/api/watchlist/{tid}/watched", json={"keep_on_watchlist": True})
    assert r.status_code == 200 and r.json()["item"]["status"]["on_watchlist"]
    assert client.post(f"/api/watchlist/{tid}/watched", json={"rating": 11}).status_code == 422
    r = client.post(f"/api/watchlist/{tid}/watched", json={"watched_on": "nope"})
    assert r.status_code == 422


def test_lookup_and_item(client, db):
    ids = seed(db)
    r = client.get("/api/items/lookup", params={"q": "glass"}).json()
    assert [x["title"] for x in r] == ["Glass Orchard"]
    item = client.get(f"/api/items/{ids['Glass Orchard']}").json()
    assert item["sources"] == ["tmdb"] and item["directors"][0]["name"] == "Bob Bergman"
    assert client.get("/api/items/9999").status_code == 404
    assert client.get("/api/items/lookup").status_code == 422
