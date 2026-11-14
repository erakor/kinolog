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


def test_unknown_host_rejected_to_stop_dns_rebinding(client):
    r = client.get("/api/health", headers={"Host": "evil.example:8765"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_host"
    assert client.get("/api/health", headers={"Host": "127.0.0.1:8765"}).status_code == 200
    assert client.get("/api/health", headers={"Host": "[::1]:8765"}).status_code == 200


def test_allow_remote_accepts_any_host(db):
    from fastapi.testclient import TestClient

    from src.interfaces.web.app import create_app

    app = create_app(db, load_model=False, allowed_hosts={"*"})
    with TestClient(app, base_url="http://anything.lan") as c:
        assert c.get("/api/health").status_code == 200
