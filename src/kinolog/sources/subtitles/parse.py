"""Subtitle parsing: SRT entries, text cleaning and scene-level chunking with timestamps."""

from __future__ import annotations

import re
from dataclasses import dataclass

from kinolog.domain import Chunk


@dataclass
class SubtitleEntry:
    index: int
    start_ms: int
    end_ms: int
    text: str


def time_to_ms(time_str: str) -> int:
    """Convert SRT time string '01:23:45,678' to milliseconds."""
    time_str = time_str.strip().replace(".", ",")
    parts = time_str.split(",")
    h_m_s = parts[0].split(":")
    hours = int(h_m_s[0])
    minutes = int(h_m_s[1])
    seconds = int(h_m_s[2])
    millis = int(parts[1]) if len(parts) > 1 else 0
    return (hours * 3600 + minutes * 60 + seconds) * 1000 + millis


def ms_to_time(ms: int) -> str:
    """Convert milliseconds to 'HH:MM:SS,mmm' format."""
    total_sec = ms // 1000
    millis = ms % 1000
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    seconds = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def clean_subtitle_text(text: str) -> str:
    r"""
    Clean SRT noise:
    - HTML formatting tags (<i>, <b>, <font...>, etc.)
    - ASS/SSA style tags ({\an8}, {\pos(x,y)}, etc.)
    - Hearing-impaired annotations ([MUSIC], (APPLAUSE), [chuckles])
    - Speaker prefixes (MARCELLO:, MAN:, etc.)
    """
    # HTML tags
    clean = re.sub(r"<[^>]+>", "", text)
    # ASS override tags
    clean = re.sub(r"\{[^\}]+\}", "", clean)
    # Hearing impaired brackets [Music playing], (screams), etc.
    clean = re.sub(r"\[[^\]]+\]", "", clean)
    clean = re.sub(r"\([^\)]+\)", "", clean)
    # Speaker prefix (e.g. "JEAN-LUC: Hello" -> "Hello")
    clean = re.sub(r"^[A-Z\s]{2,15}:\s*", "", clean)
    # Normalize whitespaces
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def parse_srt(srt_content: str) -> list[SubtitleEntry]:
    """Parse SRT string into list of clean SubtitleEntry objects."""
    blocks = re.split(r"\n\s*\n", srt_content.strip())
    entries = []

    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue

        # Header can be number or timestamp
        time_line_idx = 1 if "-->" in lines[1] else (0 if "-->" in lines[0] else None)
        if time_line_idx is None:
            continue

        time_line = lines[time_line_idx]
        parts = time_line.split("-->")
        if len(parts) != 2:
            continue

        try:
            start_ms = time_to_ms(parts[0])
            end_ms = time_to_ms(parts[1])
        except Exception:
            continue

        raw_text = " ".join(lines[time_line_idx + 1:])
        cleaned = clean_subtitle_text(raw_text)
        if cleaned:
            entries.append(SubtitleEntry(
                index=len(entries) + 1,
                start_ms=start_ms,
                end_ms=end_ms,
                text=cleaned,
            ))

    return entries


def chunk_subtitles_by_gap(
    entries: list[SubtitleEntry],
    gap_threshold_ms: int = 3500,  # 3.5 seconds of silence implies scene / dialogue turn break
    max_chunk_chars: int = 1200,
) -> list[Chunk]:
    """
    Scene-level chunking inferred from silence gaps between dialogue lines.
    """
    if not entries:
        return []

    chunks: list[Chunk] = []
    curr_lines: list[str] = []
    chunk_start_ms = entries[0].start_ms
    prev_end_ms = entries[0].end_ms
    ord_idx = 0

    for entry in entries:
        gap = entry.start_ms - prev_end_ms
        curr_len = sum(len(l) for l in curr_lines)

        # Break scene if gap exceeds threshold or chunk is getting too long
        if (gap >= gap_threshold_ms and curr_lines) or (curr_len >= max_chunk_chars):
            text_block = " ".join(curr_lines).strip()
            chunks.append(Chunk(
                text=text_block,
                ord=ord_idx,
                section_name=f"Scene {ord_idx+1} ({ms_to_time(chunk_start_ms)} - {ms_to_time(prev_end_ms)})",
                token_count=max(1, len(text_block) // 3),
                start_ms=chunk_start_ms,
                end_ms=prev_end_ms,
            ))
            ord_idx += 1
            curr_lines = []
            chunk_start_ms = entry.start_ms

        curr_lines.append(entry.text)
        prev_end_ms = entry.end_ms

    if curr_lines:
        text_block = " ".join(curr_lines).strip()
        chunks.append(Chunk(
            text=text_block,
            ord=ord_idx,
            section_name=f"Scene {ord_idx+1} ({ms_to_time(chunk_start_ms)} - {ms_to_time(prev_end_ms)})",
            token_count=max(1, len(text_block) // 3),
            start_ms=chunk_start_ms,
            end_ms=prev_end_ms,
        ))

    return chunks


def chunk_subtitles_by_window(
    entries: list[SubtitleEntry],
    window_duration_ms: int = 60000,  # 60-second fixed time window
    stride_ms: int = 45000,           # 45-second stride (15s overlap)
) -> list[Chunk]:
    """
    Time-window based subtitle chunking (e.g. 60 seconds with 15s overlap).
    """
    if not entries:
        return []

    max_time_ms = entries[-1].end_ms
    chunks: list[Chunk] = []
    ord_idx = 0
    t_start = 0

    while t_start < max_time_ms:
        t_end = t_start + window_duration_ms
        # Collect lines falling into this window
        window_entries = [e.text for e in entries if e.start_ms >= t_start and e.end_ms <= t_end]
        if window_entries:
            text_block = " ".join(window_entries).strip()
            chunks.append(Chunk(
                text=text_block,
                ord=ord_idx,
                section_name=f"Window ({ms_to_time(t_start)} - {ms_to_time(t_end)})",
                token_count=max(1, len(text_block) // 3),
                start_ms=t_start,
                end_ms=t_end,
            ))
            ord_idx += 1

        t_start += stride_ms

    return chunks
