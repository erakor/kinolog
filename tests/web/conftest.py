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
def client(db):
    app = create_app(db, load_model=False)
    with TestClient(app) as c:
        yield c
