"""Fixed-size token windows with overlap."""

from __future__ import annotations

from kinolog.domain import Chunk
from kinolog.index.chunking.base import register
from kinolog.index.chunking.runner import _estimate_tokens


def chunk_fixed_window(
    text: str,
    window_tokens: int = 256,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Fixed-size token windows with overlap."""
    # Use character approximation (3 chars/token for multilingual)
    chars_per_token = 3
    window_chars = window_tokens * chars_per_token
    overlap_chars = overlap_tokens * chars_per_token

    chunks = []
    start = 0
    ord_idx = 0

    while start < len(text):
        end = start + window_chars
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                Chunk(
                    text=chunk_text,
                    ord=ord_idx,
                    token_count=_estimate_tokens(chunk_text),
                )
            )
            ord_idx += 1
        start = end - overlap_chars
        if start >= len(text):
            break

    return chunks


@register("fixed_256_50")
def fixed_256_50(text: str) -> list[Chunk]:
    return chunk_fixed_window(text, 256, 50)


@register("fixed_512_100")
def fixed_512_100(text: str) -> list[Chunk]:
    return chunk_fixed_window(text, 512, 100)
