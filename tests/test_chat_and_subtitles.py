"""Tests for subtitle processing, chat agent context assembly, and faithfulness."""

import pytest
from src.core.db import Database
from src.core.chunkers import chunk_document
from src.ingest.enrichers.subtitles import clean_subtitle_text, parse_srt, chunk_subtitles_by_gap, chunk_subtitles_by_window
from src.interfaces.chat.agent import KinologChatAgent, assemble_context
from src.eval.faithfulness import eval_faithfulness


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
