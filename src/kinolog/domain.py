"""Plain data types and constants shared across layers."""

from __future__ import annotations

from dataclasses import dataclass

# Films at or under this runtime (minutes) count as shorts and are excluded from feature-only views.
SHORT_MAX_MIN = 40


@dataclass
class Chunk:
    text: str
    ord: int
    section_name: str | None = None
    token_count: int | None = None
    start_ms: int | None = None
    end_ms: int | None = None
