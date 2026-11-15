"""Tests for subtitle processing, chat agent context assembly, and faithfulness."""

import pytest
from kinolog.store import Database
from kinolog.core.chunkers import chunk_document
from kinolog.ingest.enrichers.subtitles import clean_subtitle_text, parse_srt, chunk_subtitles_by_gap, chunk_subtitles_by_window
from kinolog.interfaces.chat.agent import KinologChatAgent, assemble_context
from kinolog.eval.faithfulness import eval_faithfulness


SAMPLE_SRT = """1
00:01:20,000 --> 00:01:23,500
<i>[Music playing]</i> MARCELLO: Bonjour Rome!

2
00:01:24,000 --> 00:01:26,000
{\\an8}Sylvia is arriving at the airport.

3
00:01:35,000 --> 00:01:38,000
(Crowd cheers)
The fountain awaits.
"""


def test_clean_subtitle_text():
    raw = "<i>[Music playing]</i> MARCELLO: Hello! {\\an8} (Laughs)"
    clean = clean_subtitle_text(raw)
    assert clean == "Hello!"


def test_parse_srt():
    entries = parse_srt(SAMPLE_SRT)
    assert len(entries) == 3
    assert entries[0].start_ms == 80000
    assert entries[0].end_ms == 83500
    assert entries[0].text == "Bonjour Rome!"
    assert entries[1].text == "Sylvia is arriving at the airport."


def test_chunk_subtitles_by_gap():
    entries = parse_srt(SAMPLE_SRT)
    # Between entry 2 (end 86000) and entry 3 (start 95000), gap is 9000ms > 3500ms
    chunks = chunk_subtitles_by_gap(entries, gap_threshold_ms=3500)
    assert len(chunks) == 2
    assert "Bonjour Rome!" in chunks[0].text
    assert "The fountain awaits" in chunks[1].text
    assert chunks[0].start_ms == 80000


def test_chunk_subtitles_by_window():
    entries = parse_srt(SAMPLE_SRT)
    chunks = chunk_subtitles_by_window(entries, window_duration_ms=60000, stride_ms=30000)
    assert len(chunks) >= 1


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
    from kinolog.core.search import SearchResult
    from kinolog.interfaces.chat import agent as agent_mod

    db, ids = _agent_db()

    def boom(*a, **k):
        raise AssertionError("search must not be called")

    monkeypatch.setattr(agent_mod, "search", boom)
    res = [SearchResult(item_id=ids["Solaris"], chunk_id=1, score=1.0, title="Solaris",
                        year=1972, chunk_text="An astronaut visits a space station.")]
    out = agent_mod.KinologChatAgent(db).answer_query("anything", results=res)
    assert [c["title"] for c in out["citations"]] == ["Solaris"]


def test_answer_query_forwards_filters():
    from kinolog.core.search import SearchFilters

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


def test_grounding_module_is_core_and_agent_reexports():
    import kinolog.core.grounding as g
    from kinolog.interfaces.chat import agent as agent_mod

    assert agent_mod.assemble_context is g.assemble_context
    from kinolog.eval.metrics import groundedness

    assert groundedness is g.groundedness


def test_check_grounding_directly():
    from kinolog.core.grounding import assemble_context, check_grounding
    from kinolog.core.search import SearchResult

    db, ids = _agent_db()
    ctx = assemble_context([SearchResult(
        item_id=ids["Solaris"], chunk_id=1, score=1.0, title="Solaris", year=1972,
        chunk_text="An astronaut visits a space station.")])
    ok = check_grounding(db, "Solaris [^1] fits.", ctx)
    assert ok["is_fully_grounded"] and ok["citations_valid"]
    bad = check_grounding(db, "Ran [^3] fits.", ctx, mention_scope={ids["Ran"]})
    assert not bad["is_fully_grounded"] and bad["invalid_citations"] == [3]
