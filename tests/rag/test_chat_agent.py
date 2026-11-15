"""Tests for chat agent context assembly, grounding and faithfulness."""

import pytest

from kinolog.eval.suites.faithfulness import eval_faithfulness
from kinolog.index.chunking import chunk_document
from kinolog.rag.agent import KinologChatAgent
from kinolog.store import Database


@pytest.fixture
def db_for_chat():
    db = Database(":memory:")
    id1 = db.upsert_item("film", "La Dolce Vita", 1960)
    doc1 = db.upsert_document(id1, "tmdb", "en", "A decadent journalist wanders through high society Rome.")
    chunk_document(db, doc1, strategy="whole")

    id2 = db.upsert_item("film", "8½", 1963)
    doc2 = db.upsert_document(id2, "tmdb", "en", "Director Guido Anselmi suffers creative blockage.")
    chunk_document(db, doc2, strategy="whole")

    yield db
    db.close()


def test_chat_agent_answer_and_grounding(db_for_chat):
    agent = KinologChatAgent(db_for_chat)
    res = agent.answer_query("Tell me about films set in Rome")
    assert "La Dolce Vita" in res["answer"]
    assert res["is_fully_grounded"] is True
    assert len(res["citations"]) > 0


def test_eval_faithfulness(db_for_chat):
    prompts = [
        {"id": 1, "question": "Which films are set in Rome?", "expected_item_titles": ["La Dolce Vita"]},
        {"id": 2, "question": "Tell me about a filmmaker having a creative crisis", "expected_item_titles": ["8½"]},
    ]
    results = eval_faithfulness(db_for_chat, prompts=prompts)
    assert len(results) == 2
    metrics = {r.metric: r.value for r in results}
    assert metrics["pct_fully_grounded"] == 100.0
    assert metrics["mean_groundedness"] == 1.0


def _agent_db():
    db = Database(":memory:")
    ids = {}
    for title, year, text in [
        ("Solaris", 1972, "An astronaut visits a space station above an ocean planet."),
        ("Stalker", 1979, "A guide leads two men through a forbidden zone."),
        ("Ran", 1985, "An aging warlord divides his kingdom among his sons."),
    ]:
        i = db.upsert_item("film", title, year)
        doc = db.upsert_document(i, "tmdb", "en", text)
        chunk_document(db, doc, strategy="whole")
        ids[title] = i
    return db, ids


def test_answer_query_uses_prefetched_results_without_searching(monkeypatch):
    from kinolog.rag import agent as agent_mod
    from kinolog.retrieval import SearchResult

    db, ids = _agent_db()

    def boom(*a, **k):
        raise AssertionError("search must not be called")

    monkeypatch.setattr(agent_mod, "search", boom)
    res = [SearchResult(item_id=ids["Solaris"], chunk_id=1, score=1.0, title="Solaris",
                        year=1972, chunk_text="An astronaut visits a space station.")]
    out = agent_mod.KinologChatAgent(db).answer_query("anything", results=res)
    assert [c["title"] for c in out["citations"]] == ["Solaris"]


def test_answer_query_forwards_filters():
    from kinolog.retrieval import SearchFilters

    db, ids = _agent_db()
    db.execute("UPDATE items SET runtime_min = 167 WHERE title = 'Solaris'")
    db.execute("UPDATE items SET runtime_min = 90 WHERE title = 'Stalker'")
    out = KinologChatAgent(db).answer_query(
        "space zone kingdom", filters=SearchFilters(runtime_max=100)
    )
    assert {c["title"] for c in out["citations"]} == {"Stalker"}


def test_scoped_mention_check_and_citation_validation():
    db, ids = _agent_db()

    def gen(question, context):
        return "Consider Solaris [^1] and also Ran [^4]."

    agent = KinologChatAgent(db)
    out = agent.answer_query(
        "ocean planet", generator_fn=gen, search_mode="bm25",
        mention_scope={ids["Solaris"], ids["Ran"]},
    )
    assert set(out["mentioned_item_ids"]) == {ids["Solaris"], ids["Ran"]}
    assert out["is_fully_grounded"] is False  # Ran was never retrieved
    assert out["invalid_citations"] == [4] and out["citations_valid"] is False

    # Stalker is mentioned but outside the scope: not counted
    def gen2(q, c):
        return "Solaris [^1] and Stalker."

    out2 = agent.answer_query("ocean planet", generator_fn=gen2, mention_scope={ids["Solaris"]})
    assert out2["mentioned_item_ids"] == [ids["Solaris"]]
    assert out2["is_fully_grounded"] and out2["citations_valid"]


def test_context_module_is_core_and_agent_reexports():
    from kinolog.rag import agent as agent_mod
    from kinolog.rag import context

    assert agent_mod.assemble_context is context.assemble_context


def test_check_grounding_directly():
    from kinolog.rag.context import assemble_context
    from kinolog.rag.grounding import check_grounding
    from kinolog.retrieval import SearchResult

    db, ids = _agent_db()
    ctx = assemble_context([SearchResult(
        item_id=ids["Solaris"], chunk_id=1, score=1.0, title="Solaris", year=1972,
        chunk_text="An astronaut visits a space station.")])
    ok = check_grounding(db, "Solaris [^1] fits.", ctx)
    assert ok["is_fully_grounded"] and ok["citations_valid"]
    bad = check_grounding(db, "Ran [^3] fits.", ctx, mention_scope={ids["Ran"]})
    assert not bad["is_fully_grounded"] and bad["invalid_citations"] == [3]
