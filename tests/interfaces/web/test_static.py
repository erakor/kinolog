import re
from pathlib import Path

from fastapi.testclient import TestClient

from kinolog.interfaces.web.app import BUILD_HINT, create_app

FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
EXTERNAL_URL = re.compile(
    r"""(?:src|href)=["']https?://|url\(\s*["']?https?://|@import\s+["']?https?://"""
    r"""|fetch\(\s*["'`]https?://|from\s+["']https?://"""
)


def test_index_served(db, tmp_path):
    (tmp_path / "index.html").write_text("<title>Kinolog</title>")
    app = create_app(db, load_model=False, dist_dir=tmp_path)
    with TestClient(app, base_url="http://localhost") as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "Kinolog" in r.text


def test_missing_build_returns_503_with_hint(db, tmp_path):
    app = create_app(db, load_model=False, dist_dir=tmp_path / "nope")
    with TestClient(app, base_url="http://localhost") as c:
        r = c.get("/")
        assert r.status_code == 503
        assert BUILD_HINT in r.text
        assert c.get("/api/health").status_code == 200  # the API still works


def test_assets_served(db, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.css").write_text(":root { --color-accent: red; }")
    app = create_app(db, load_model=False, dist_dir=tmp_path)
    with TestClient(app, base_url="http://localhost") as c:
        r = c.get("/assets/app.css")
    assert r.status_code == 200
    assert "--color-accent" in r.text


def _source_files():
    files = [FRONTEND_DIR / "index.html"]
    for p in (FRONTEND_DIR / "src").rglob("*"):
        if p.is_file() and p.suffix in {".html", ".css", ".ts", ".tsx"}:
            files.append(p)
    return [p for p in files if "node_modules" not in p.parts]


def test_no_external_urls_in_frontend_sources():
    files = _source_files()
    assert files, "frontend sources not found"
    for p in files:
        assert not EXTERNAL_URL.search(p.read_text()), f"external URL in {p}"


def test_no_dangerously_set_inner_html():
    for p in _source_files():
        assert "dangerouslySetInnerHTML" not in p.read_text(), f"unsafe HTML in {p}"


def test_light_theme_only():
    css = (Path(FRONTEND_DIR) / "src/styles/tokens.css").read_text()
    assert "prefers-color-scheme" not in css
    assert "--color-accent" in css

