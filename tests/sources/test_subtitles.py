"""Tests for subtitle parsing, cleaning and scene chunking."""

from kinolog.sources.subtitles.parse import (
    chunk_subtitles_by_gap,
    chunk_subtitles_by_window,
    clean_subtitle_text,
    parse_srt,
)

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
