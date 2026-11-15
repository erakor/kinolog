from tests.interfaces.web.seed import seed


def test_empty_db_returns_empty_list(client):
    r = client.get("/api/collections/directors")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0 and body["items"] == []
    assert body["summary"] == {"tracked": 0, "above_50": 0, "completed": 0}


def test_list_sorted_by_pct_with_films(client, db):
    seed(db)
    body = client.get("/api/collections/directors", params={"include_films": True}).json()
    names = [d["name"] for d in body["items"]]
    assert names == ["Bob Bergman", "Ann Auteur"]  # Bob 2/3 (short excluded), Ann 2/5
    bob = body["items"][0]
    assert (bob["seen"], bob["total"]) == (2, 3)
    titles = [f["title"] for f in bob["films"]]
    assert titles == ["Salt and Silence", "Winter Letters", "Glass Orchard"]
    assert body["summary"]["tracked"] == 2


def test_status_filter_and_query(client, db):
    seed(db)
    r = client.get("/api/collections/directors", params={"status": "completed"}).json()
    assert r["items"] == []
    r = client.get("/api/collections/directors", params={"q": "corridor"}).json()
    assert [d["name"] for d in r["items"]] == ["Ann Auteur"]
    assert client.get("/api/collections/directors", params={"sort": "bogus"}).status_code == 422


def test_detail_and_404(client, db):
    seed(db)
    pid = db.execute("SELECT id FROM people WHERE name='Ann Auteur'").fetchone()["id"]
    d = client.get(f"/api/collections/directors/{pid}").json()
    assert d["total"] == 5 and d["seen"] == 2
    unseen = [f for f in d["films"] if not f["seen"]]
    assert unseen and all(f["after_pct"] == 60.0 for f in unseen)
    assert client.get("/api/collections/directors/9999").status_code == 404
