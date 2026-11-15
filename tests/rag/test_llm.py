from types import SimpleNamespace

from kinolog.rag.llm import SYSTEM_PROMPT, build_generator


class FakeClient:
    def __init__(self, text="Fine [^1].", stop="end_turn", raises=None):
        self.calls = []
        self._text, self._stop, self._raises = text, stop, raises
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self._raises:
            raise self._raises
        return SimpleNamespace(
            stop_reason=self._stop, content=[SimpleNamespace(type="text", text=self._text)]
        )


def test_generator_calls_client_with_context_and_returns_text():
    c = FakeClient()
    gen = build_generator(client=c, model="m")
    assert gen("a query", "CONTEXT [^1]") == "Fine [^1]."
    call = c.calls[0]
    assert call["model"] == "m" and call["system"] == SYSTEM_PROMPT
    assert "a query" in call["messages"][0]["content"]
    assert "CONTEXT [^1]" in call["messages"][0]["content"]
    assert call["output_config"] == {"effort": "low"} and "thinking" not in call


def test_refusal_truncation_and_errors_return_empty():
    assert build_generator(client=FakeClient(stop="refusal"))("q", "c") == ""
    assert build_generator(client=FakeClient(stop="max_tokens"))("q", "c") == ""
    assert build_generator(client=FakeClient(raises=RuntimeError("boom")))("q", "c") == ""


def test_default_model_from_env(monkeypatch):
    monkeypatch.setenv("KINOLOG_LLM_MODEL", "custom-model")
    c = FakeClient()
    build_generator(client=c)("q", "c")
    assert c.calls[0]["model"] == "custom-model"
