from tests.interfaces.web.seed import seed


def test_list_with_summary_and_filters(client, db):
    seed(db)
    body = client.get("/api/log").json()
    assert body["total"] == 4  # four seen films in the seed
    assert body["summary"]["count"] == 4
    assert body["summary"]["avg_rating"] == 7.5  # two 8s and two 7s
    dates = [e["watched_on"] for e in body["entries"]]
    assert dates == sorted(dates, reverse=True)
    r = client.get("/api/log", params={"min_rating": 8}).json()
    assert r["total"] == 2
    r = client.get("/api/log", params={"year": 2010}).json()
    assert [e["item"]["title"] for e in r["entries"]] == ["Quiet Harbor"]
    r = client.get("/api/log", params={"q": "bergman"}).json()
    assert r["total"] == 2
    assert client.get("/api/log", params={"month": 13}).status_code == 422


def test_create_patch_delete(client, db):
    ids = seed(db)
    iid = ids["Midnight Ferry"]
    r = client.post("/api/log", json={"item_id": iid, "watched_on": "2024-09-09", "rating": 6})
    assert r.status_code == 201
    entry = r.json()
    assert entry["source"] == "manual" and entry["item"]["status"]["seen"]
    eid = entry["entry_id"]

    r = client.patch(f"/api/log/{eid}", json={"rating": 9, "rewatch": True})
    assert r.json()["rating"] == 9 and r.json()["rewatch"] is True
    r = client.patch(f"/api/log/{eid}", json={"rating": None})
    assert r.json()["rating"] is None

    assert client.delete(f"/api/log/{eid}").status_code == 204
    assert client.get("/api/log", params={"q": "ferry"}).json()["total"] == 0
    looked = client.get("/api/items/lookup", params={"q": "ferry"}).json()
    assert looked[0]["status"]["seen"] is False
    assert client.delete(f"/api/log/{eid}").status_code in (204, 404)
    assert client.patch(f"/api/log/{eid}", json={"rating": 5}).status_code == 404


def test_create_validation(client, db):
    ids = seed(db)
    iid = ids["Midnight Ferry"]
    assert client.post("/api/log", json={"item_id": iid, "watched_on": "9/9/24"}).status_code == 422
    assert (
        client.post(
            "/api/log", json={"item_id": iid, "watched_on": "2024-01-01", "rating": 0}
        ).status_code
        == 422
    )
    missing = {"item_id": 9999, "watched_on": "2024-01-01"}
    assert client.post("/api/log", json=missing).status_code == 404


def test_logging_dequeues(client, db):
    ids = seed(db)
    tid = ids["Glass Orchard"]
    client.post("/api/log", json={"item_id": tid, "watched_on": "2024-01-02"})
    assert client.get("/api/watchlist").json()["total"] == 2


def test_rating_and_liked_put(client, db):
    ids = seed(db)
    iid = ids["Midnight Ferry"]
    r = client.put(f"/api/items/{iid}/rating", json={"rating": 7})
    assert r.json()["status"]["rating"] == 7
    assert client.put(f"/api/items/{iid}/rating", json={"rating": 11}).status_code == 422
    cleared = client.put(f"/api/items/{iid}/rating", json={"rating": None}).json()
    assert cleared["status"]["rating"] is None
    assert client.put(f"/api/items/{iid}/liked", json={"liked": True}).json()["status"]["liked"]
    assert client.put("/api/items/9999/liked", json={"liked": True}).status_code == 404


def test_dates_are_normalised_or_rejected(client, db):
    ids = seed(db)
    iid = ids["Midnight Ferry"]
    r = client.post("/api/log", json={"item_id": iid, "watched_on": "20240101"})
    assert r.status_code == 201 and r.json()["watched_on"] == "2024-01-01"
    r = client.post("/api/log", json={"item_id": iid, "watched_on": "2024-W01-1"})
    assert r.status_code == 201 and r.json()["watched_on"] == "2024-01-01"
    assert client.post("/api/log", json={"item_id": iid, "watched_on": "nope"}).status_code == 422
