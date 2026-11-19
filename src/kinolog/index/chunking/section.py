"""Section-aware chunking, with or without a title prefix."""

from __future__ import annotations

from kinolog.domain import Chunk
from kinolog.index.chunking.base import register
from kinolog.index.chunking.runner import _estimate_tokens


def chunk_by_section(
    text: str,
    prepend_title: bool = True,
) -> list[Chunk]:
    """
    Section-aware chunking.

    Splits on lines that look like section headers (lines ending with ':' or
    lines that are short and followed by longer content).
    """
    lines = text.split("\n")
    if not lines:
        return []

    # Extract title (first non-empty line)
    title_line = ""
    for line in lines:
        if line.strip():
            title_line = line.strip()
            break

    # Find sections: lines that look like "Category:" or short header lines
    sections = []
    current_name = "header"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Detect section headers
        if stripped.endswith(":") and len(stripped) < 60 and len(stripped) > 2:
            if current_lines:
                sections.append((current_name, "\n".join(current_lines).strip()))
            current_name = stripped.rstrip(":")
            current_lines = []
        else:
            current_lines.append(line)

    # Don't forget the last section
    if current_lines:
        sections.append((current_name, "\n".join(current_lines).strip()))

    # Build chunks
    chunks = []
    for i, (section_name, section_text) in enumerate(sections):
        if not section_text.strip():
            continue
        text_with_prefix = section_text
        if prepend_title and section_name != "header":
            text_with_prefix = f"{title_line}\n[{section_name}]\n{section_text}"
        chunks.append(
            Chunk(
                text=text_with_prefix,
                ord=i,
                section_name=section_name,
                token_count=_estimate_tokens(text_with_prefix),
            )
        )

    return chunks


@register("section")
def section(text: str) -> list[Chunk]:
    return chunk_by_section(text, prepend_title=True)


@register("section_no_prefix")
def section_no_prefix(text: str) -> list[Chunk]:
    return chunk_by_section(text, prepend_title=False)
