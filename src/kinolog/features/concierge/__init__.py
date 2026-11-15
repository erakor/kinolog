"""Concierge: deterministic constraint parsing, filtered retrieval and grounded picks.

The parser is regex + small lexicons (no LLM) so it is testable and works offline.
Matched constraint phrases are removed from the residual query, because the BM25 index
contains literal text like "Runtime: 90 minutes" that such phrases would otherwise match.
"""

from kinolog.features.concierge.constraints import (
    Chip,
    ParsedQuery,
    parse_constraints,
    to_search_filters,
)
from kinolog.features.concierge.pick import pick

__all__ = ["Chip", "ParsedQuery", "parse_constraints", "pick", "to_search_filters"]
