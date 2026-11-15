"""The Concierge falls back to the template rationale when the LLM output is unusable."""

from kinolog.rag.llm import build_generator
from tests.rag.test_llm import FakeClient


def test_empty_output_triggers_template_fallback_end_to_end(db):
    from fastapi.testclient import TestClient

    from kinolog.interfaces.web.app import create_app
    from tests.interfaces.web.seed import seed

    seed(db)
    gen = build_generator(client=FakeClient(raises=OSError()))
    app = create_app(db, load_model=False, generator=gen)
    with TestClient(app, base_url="http://localhost") as c:
        body = c.post("/api/concierge", json={"query": "ferry mystery"}).json()
    assert body["picks"][0]["rationale"]["generator"] == "template"
    assert any(d.startswith("llm_ungrounded") for d in body["degraded"])
