"""Shared fixtures for web tests. Skipped when the `web` extra is not installed."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

from src.core.db import Database  # noqa: E402
from src.interfaces.web.app import create_app  # noqa: E402


@pytest.fixture
def db():
    d = Database(":memory:", check_same_thread=False)
    yield d
    d.close()


@pytest.fixture
def client(db, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Kinolog</title>")
    app = create_app(db, load_model=False, dist_dir=tmp_path)
    with TestClient(app, base_url="http://localhost") as c:
        yield c
