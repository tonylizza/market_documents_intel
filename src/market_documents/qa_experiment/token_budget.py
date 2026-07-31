"""Milestone 7B.1d Phase 4: deterministic, documented reduction policy for
chunks that exceed the pinned embedding model's real 512-token ceiling
(`embedding_config.MAXIMUM_MODEL_TOKENS`). Never silent -- every reduction is
recorded on `ChunkCandidate.truncation_policy`, and the research-layer
policy of *skipping* rather than truncating oversized canonical passages
(`services/passage_embedding.py::_run_embedding`) is deliberately NOT
replicated here: a chunk that only exists to add context around a passage
that already has its own canonical embedding is more useful reduced than
dropped, since the anchor passage always remains fully searchable via
strategy A regardless of what happens to its chunk variants.

`count_tokens` is always injected (the real pinned tokenizer in production,
a cheap deterministic fake in unit tests) -- this module never imports
`sentence_transformers` itself.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from market_documents.qa_experiment.models import (
    ROLE_ANCHOR,
    ROLE_EARLIER_SIDE,
    ROLE_HEADING_CONTEXT,
    ROLE_LATER_SIDE,
    ROLE_NEXT,
    ROLE_PREVIOUS,
    ChunkCandidate,
    ChunkMember,
)
from market_documents.qa_experiment.chunk_strategies import (
    STRATEGY_COMPARISON_PAIR,
)

MAXIMUM_MODEL_TOKENS = 512

# Drop order for neighbor-style strategies (B/C/D/E): least-central member
# first. HEADING_CONTEXT drops before PREVIOUS/NEXT because a missing
# heading label degrades gracefully (the anchor's own text still stands
# alone), whereas dropping a neighbor changes which strategy the chunk
# effectively represents -- both are already recorded via `truncation_policy`
# either way, so the ordering only affects how much text survives.
_NEIGHBOR_DROP_ORDER = (ROLE_HEADING_CONTEXT, ROLE_NEXT, ROLE_PREVIOUS)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _word_trim_from_end(text: str, count_tokens: Callable[[str], int], budget: int) -> str:
    """Last-resort fallback for text with no `.!?`-delimited sentences at
    all (common in table-like or numeric-heavy financial passages) --
    `_sentence_trim_from_end` cannot reduce a single run-on "sentence", so
    this drops trailing whitespace-delimited words instead. Always leaves at
    least one word, even if that word alone still exceeds `budget` -- a
    single token can never be reduced further, and the 512-token ceiling is
    a soft target here, not a hard invariant the caller can always satisfy."""
    words = text.split()
    while len(words) > 1 and count_tokens(" ".join(words)) > budget:
        words = words[:-1]
    return " ".join(words)


def _word_trim_from_start(text: str, count_tokens: Callable[[str], int], budget: int) -> str:
    words = text.split()
    while len(words) > 1 and count_tokens(" ".join(words)) > budget:
        words = words[1:]
    return " ".join(words)


def _sentence_trim_from_end(text: str, count_tokens: Callable[[str], int], budget: int) -> str:
    sentences = _SENTENCE_SPLIT.split(text)
    while len(sentences) > 1 and count_tokens(" ".join(sentences)) > budget:
        sentences = sentences[:-1]
    reduced = " ".join(sentences)
    if count_tokens(reduced) > budget:
        reduced = _word_trim_from_end(reduced, count_tokens, budget)
    return reduced


def _sentence_trim_from_start(text: str, count_tokens: Callable[[str], int], budget: int) -> str:
    sentences = _SENTENCE_SPLIT.split(text)
    while len(sentences) > 1 and count_tokens(" ".join(sentences)) > budget:
        sentences = sentences[1:]
    reduced = " ".join(sentences)
    if count_tokens(reduced) > budget:
        reduced = _word_trim_from_start(reduced, count_tokens, budget)
    return reduced


def enforce_token_budget(
    candidate: ChunkCandidate,
    count_tokens: Callable[[str], int],
    text_by_passage_id: dict,
    heading_text: str | None = None,
    max_tokens: int = MAXIMUM_MODEL_TOKENS,
) -> ChunkCandidate:
    """Reduce `candidate` in place (returns the same, mutated object) until
    `count_tokens(candidate.text) <= max_tokens`, or until only the anchor
    remains and even that must be sentence-trimmed as a last resort.

    `text_by_passage_id` supplies each member passage's raw text so a
    neighbor-style candidate can be rebuilt after dropping a member; H
    (comparison pair) and F (fixed window) candidates use a different,
    simpler reduction path since they already carry their exact text.
    """
    if count_tokens(candidate.text) <= max_tokens:
        return candidate

    if candidate.strategy == STRATEGY_COMPARISON_PAIR:
        earlier_id = next(m.passage_id for m in candidate.members if m.role == ROLE_EARLIER_SIDE)
        later_id = next(m.passage_id for m in candidate.members if m.role == ROLE_LATER_SIDE)
        earlier_text = text_by_passage_id[earlier_id]
        later_text = text_by_passage_id[later_id]
        # Trim the EARLIER side first (from its start -- oldest content),
        # then the LATER side (from its end), alternating, never dropping
        # either side entirely -- a comparison chunk with only one side left
        # is no longer a comparison chunk.
        budget_each = max_tokens // 2
        earlier_reduced = _sentence_trim_from_start(earlier_text, count_tokens, budget_each)
        later_reduced = _sentence_trim_from_end(later_text, count_tokens, budget_each)
        candidate.text = (
            f"Earlier report (reduced): {earlier_reduced}\n\nLater report (reduced): {later_reduced}"
        )
        candidate.truncation_policy = "trimmed_both_sides"
        if count_tokens(candidate.text) > max_tokens:
            candidate.text = _sentence_trim_from_end(candidate.text, count_tokens, max_tokens)
            candidate.truncation_policy = "trimmed_both_sides_and_result"
        return candidate

    if candidate.strategy.startswith("FIXED_TOKEN_WINDOW"):
        candidate.text = _sentence_trim_from_end(candidate.text, count_tokens, max_tokens)
        candidate.truncation_policy = "window_trimmed"
        return candidate

    # Neighbor-style strategies (B/C/D/E): drop whole outer members first.
    surviving_roles = {m.role for m in candidate.members}
    members = list(candidate.members)
    for role_to_drop in _NEIGHBOR_DROP_ORDER:
        if role_to_drop not in surviving_roles:
            continue
        members = [m for m in members if m.role != role_to_drop]
        surviving_roles.discard(role_to_drop)
        rebuilt = _rebuild_text_from_members(members, text_by_passage_id, heading_text, surviving_roles)
        if count_tokens(rebuilt) <= max_tokens:
            candidate.members = tuple(members)
            candidate.text = rebuilt
            candidate.truncation_policy = f"dropped_{role_to_drop.lower()}"
            return candidate
        candidate.members = tuple(members)
        candidate.text = rebuilt

    # Only ANCHOR remains and it alone still exceeds the budget -- last
    # resort, sentence-trim the anchor's own text.
    anchor_id = next(m.passage_id for m in candidate.members if m.role == ROLE_ANCHOR)
    candidate.text = _sentence_trim_from_end(text_by_passage_id[anchor_id], count_tokens, max_tokens)
    candidate.truncation_policy = "anchor_trimmed"
    return candidate


def _rebuild_text_from_members(
    members: list[ChunkMember], text_by_passage_id: dict, heading_text: str | None, surviving_roles: set[str]
) -> str:
    ordered = sorted(members, key=lambda m: m.passage_order)
    prefix = f"Heading: {heading_text}\n" if heading_text and ROLE_HEADING_CONTEXT in surviving_roles else ""
    body = "\n\n".join(text_by_passage_id[m.passage_id] for m in ordered if m.role != ROLE_HEADING_CONTEXT)
    return f"{prefix}{body}"
