from tests.web.seed import seed


def test_parse_endpoint(client):
    r = client.post("/api/concierge/parse", json={"query": "tense drama under 90 minutes"})
    assert r.status_code == 200
    body = r.json()
    assert body["filters"]["runtime_max"] == 90
    assert body["residual_query"] == "tense drama"
    assert body["chips"][0]["kind"] == "runtime_max"


def test_concierge_bm25_with_degraded_and_citations(client, db):
    seed(db)
    r = client.post("/api/concierge", json={"query": "ferry mystery", "limit": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["mode_used"] == "bm25"
    assert any(d.startswith(("no_vector", "no_model")) for d in body["degraded"])
    assert "no_llm: template rationale" in body["degraded"]
    top = body["picks"][0]
    assert top["item"]["title"] == "Midnight Ferry"
    rat = top["rationale"]
    assert rat["generator"] == "template" and rat["citations"]
    assert rat["citations"][0]["snippet"]
    assert top["completion"][0]["name"] == "Ann Auteur"


def test_runtime_constraint_honored(client, db):
    seed(db)
    body = client.post("/api/concierge", json={"query": "something under 90 minutes"}).json()
    assert [p["item"]["title"] for p in body["picks"]] == ["Brief Encounter Again"]
    assert all(p["item"]["runtime_min"] <= 90 for p in body["picks"])


def test_scope_watchlist_only(client, db):
    seed(db)
    body = client.post(
        "/api/concierge", json={"query": "give me a movie", "scope": "watchlist", "limit": 10}
    ).json()
    assert {p["item"]["title"] for p in body["picks"]} == {
        "The Long Corridor", "Brief Encounter Again", "Glass Orchard",
    }
    assert all(p["item"]["status"]["on_watchlist"] for p in body["picks"])


def test_empty_result_explains_filters(client, db):
    seed(db)
    r = client.post("/api/concierge", json={"query": "ferry mystery under 20 minutes"})
    assert r.status_code == 200
    body = r.json()
    assert body["picks"] == []
    assert body["empty"]["relax"][0]["filter"] == "runtime"


def test_nonsense_query_is_empty_state_not_error(client, db):
    seed(db)
    r = client.post("/api/concierge", json={"query": "zzzzqqq xyzzy"})
    assert r.status_code == 200 and r.json()["picks"] == []


def test_validation(client):
    assert client.post("/api/concierge", json={"query": ""}).status_code == 422
    assert client.post("/api/concierge", json={"query": "x", "scope": "bogus"}).status_code == 422
    assert client.post("/api/concierge", json={"query": "x", "limit": 99}).status_code == 422


def test_llm_generator_is_used_when_valid(db):
    from fastapi.testclient import TestClient

    from kinolog.interfaces.web.app import create_app

    seed(db)
    app = create_app(db, load_model=False, generator=lambda q, ctx: "A tense ferry mystery [^1].")
    with TestClient(app, base_url="http://localhost") as c:
        body = c.post("/api/concierge", json={"query": "ferry mystery"}).json()
    assert body["picks"][0]["rationale"]["generator"] == "llm"
    assert "no_llm: template rationale" not in body["degraded"]


def test_suggestions_and_overview(client, db):
    seed(db)
    prompts = client.get("/api/concierge/suggestions").json()["prompts"]
    assert any("Bob Bergman" in p for p in prompts) and len(prompts) <= 5

    o = client.get("/api/concierge/overview").json()
    assert o["watchlist"] == {"count": 3, "total_minutes": 329, "short_count": 1}
    assert o["log"]["count"] == 4 and o["log"]["avg_rating"] == 3.8
    assert o["directors"]["tracked"] == 2
    assert o["closest"]["name"] == "Bob Bergman" and o["closest"]["pct"] == 66.7
    q = o["radar"][0]["quickest"]
    assert q["title"] == "Glass Orchard" and q["after_pct"] == 100.0 and q["on_watchlist"]


def test_overview_on_empty_db(client):
    o = client.get("/api/concierge/overview").json()
    assert o["closest"] is None and o["radar"] == [] and o["log"]["avg_rating"] is None
