import re
from pathlib import Path

from src.interfaces.web.app import STATIC_DIR


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Kinolog" in r.text


def test_tokens_served(client):
    r = client.get("/static/css/tokens.css")
    assert r.status_code == 200
    assert "--color-accent" in r.text


def test_no_external_urls_in_static_files():
    pattern = re.compile(r"""(?:src|href)=["']https?://|url\(\s*["']?https?://|@import\s+["']?https?://|fetch\(\s*["']https?://""")
    for p in Path(STATIC_DIR).rglob("*"):
        if p.is_file() and p.suffix in {".html", ".css", ".js"}:
            assert not pattern.search(p.read_text()), f"external URL in {p}"


def test_light_theme_only():
    css = (Path(STATIC_DIR) / "css/tokens.css").read_text()
    assert "prefers-color-scheme" not in css
