"""Optional LLM rationale generator (``llm`` extra). Opt-in only: it sends the user's query and
retrieved chunk text to the Anthropic API.

The returned callable has the ``generator_fn(question, context_text) -> str`` shape used by
the Concierge. Anything unusual (refusal, truncation, API error) returns "" so the caller's
grounding check rejects it and the deterministic template is used instead.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
MAX_TOKENS = 600

SYSTEM_PROMPT = (
    "You write a short rationale (2 or 3 sentences) for why one film fits the user's request. "
    "Use only the sources and facts in the provided context. Every statement taken from a "
    "source must end with its citation marker exactly as shown, like [^1]; never invent a "
    "marker. Do not mention any other film by title. If the context does not support a "
    "claim, leave it out."
)


def build_generator(
    client: Any = None, model: str | None = None
) -> Callable[[str, str], str] | None:
    """Return a generator, or None if the SDK is not installed."""
    if client is None:
        try:
            import anthropic
        except ImportError:
            logger.warning("anthropic is not installed; install kinolog[llm]")
            return None
        client = anthropic.Anthropic()  # resolves env key or an `ant auth login` profile
    model_id = model or os.environ.get("KINOLOG_LLM_MODEL", DEFAULT_MODEL)

    def generate(question: str, context_text: str) -> str:
        try:
            response = client.messages.create(
                model=model_id,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                output_config={"effort": "low"},
                messages=[{
                    "role": "user",
                    "content": f"Request: {question}\n\n{context_text}\n\nWrite the rationale.",
                }],
            )
        except Exception as e:  # network, auth, rate limit: degrade to the template
            logger.warning("LLM rationale failed: %s", type(e).__name__)
            return ""
        if getattr(response, "stop_reason", None) != "end_turn":
            return ""  # refusal or truncation
        return "".join(b.text for b in response.content if getattr(b, "type", "") == "text").strip()

    return generate
