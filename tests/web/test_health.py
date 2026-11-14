def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["model_loaded"] is False
    assert body["model_enabled"] is False
    assert body["llm_configured"] is False
    assert body["taste_available"] is False
    assert "items" in body["counts"]


def test_cross_origin_write_rejected(client):
    r = client.post("/api/health", headers={"Origin": "http://evil.example"}, json={})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "cross_origin"


def test_non_json_body_rejected(client):
    r = client.post("/api/health", content="a=b", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415


def test_unknown_api_path_is_json_404(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_404"
