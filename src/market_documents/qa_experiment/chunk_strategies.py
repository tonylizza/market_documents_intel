"""Milestone 7B.1d Phase 2-4: deterministic Q&A retrieval-chunk construction.

Strategy A (CANONICAL_PASSAGE) is not built here -- it is the existing
`app.passage_embeddings` row, reused as-is by the evaluation harness as the
baseline. Every function below builds one of the remaining prioritized
strategies (per the Phase-1 forensic diagnosis): B (HEADING_PLUS_PASSAGE),
C (PREVIOUS_PLUS_CURRENT), D (CURRENT_PLUS_NEXT), E (LOCAL_WINDOW),
F (FIXED_TOKEN_WINDOW_256_64), H (COMPARISON_PAIR).

Rules enforced by construction (never crossed):
- never cross a report or company boundary;
- preserve passage order;
- preserve every member passage's id/role for full mapping traceability;
- deterministic given the same input passage rows -- no randomness, no
  wall-clock dependence.

Token-limit enforcement (the 512-token model ceiling) is intentionally NOT
done here -- these builders produce the "ideal" unbounded chunk text;
`token_budget.enforce_token_budget` reduces it afterward using a real
tokenizer, so construction logic stays pure and testable without loading the
embedding model.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable, Sequence

from market_documents.qa_experiment.models import (
    ROLE_ANCHOR,
    ROLE_EARLIER_SIDE,
    ROLE_HEADING_CONTEXT,
    ROLE_LATER_SIDE,
    ROLE_NEXT,
    ROLE_PREVIOUS,
    ROLE_TOKEN_MEMBER,
    ChunkCandidate,
    ChunkMember,
    ComparisonContext,
    ComparisonRow,
    PassageRow,
)

STRATEGY_HEADING_PLUS_PASSAGE = "HEADING_PLUS_PASSAGE"
STRATEGY_PREVIOUS_PLUS_CURRENT = "PREVIOUS_PLUS_CURRENT"
STRATEGY_CURRENT_PLUS_NEXT = "CURRENT_PLUS_NEXT"
STRATEGY_LOCAL_WINDOW = "LOCAL_WINDOW"
STRATEGY_FIXED_TOKEN_WINDOW_256_64 = "FIXED_TOKEN_WINDOW_256_64"
STRATEGY_COMPARISON_PAIR = "COMPARISON_PAIR"

ALL_STRATEGIES = (
    STRATEGY_HEADING_PLUS_PASSAGE,
    STRATEGY_PREVIOUS_PLUS_CURRENT,
    STRATEGY_CURRENT_PLUS_NEXT,
    STRATEGY_LOCAL_WINDOW,
    STRATEGY_FIXED_TOKEN_WINDOW_256_64,
    STRATEGY_COMPARISON_PAIR,
)

# Comparisons where only one side exists carry no retrieval-recall value for
# a *pair* chunk -- NEW/REMOVED rows have one of earlier/later_passage_id
# null and are excluded by the None-check in build_comparison_pair_chunks
# itself, not by filtering on this set.
_VALID_BOTH_SIDES_ALIGNMENT_STATUSES = frozenset(
    {"UNCHANGED", "LIGHTLY_MODIFIED", "SUBSTANTIALLY_MODIFIED", "AMBIGUOUS"}
)


def resolve_effective_heading(
    report_passages_sorted: Sequence[PassageRow], target_index: int
) -> tuple[str | None, uuid.UUID | None]:
    """Nearest heading for `target_index`, walking backward within the same
    report -- mirrors the research-layer segmentation rule where
    `heading_text` is only stamped on the first passage of a heading-started
    run (`passage_segmentation.py::_pack_run_into_passages`). Returns
    `(heading_text, source_passage_id)`; `source_passage_id` is `None` when
    the target passage owns its own heading (no separate HEADING_CONTEXT
    member needed), and also `None` when no heading exists at all."""
    for i, p in enumerate(report_passages_sorted):
        if p.passage_index == target_index:
            if p.heading:
                return p.heading, None
            for prior in reversed(report_passages_sorted[:i]):
                if prior.heading:
                    return prior.heading, prior.id
            return None, None
    return None, None


def _neighbor(report_passages_sorted: Sequence[PassageRow], target_index: int, direction: int) -> PassageRow | None:
    for i, p in enumerate(report_passages_sorted):
        if p.passage_index == target_index:
            j = i + direction
            return report_passages_sorted[j] if 0 <= j < len(report_passages_sorted) else None
    return None


def build_heading_plus_passage_chunks(report_passages_sorted: Sequence[PassageRow]) -> list[ChunkCandidate]:
    """B: `Heading: ...\\nContent: ...` for every passage with a resolvable
    heading. Passages with no heading anywhere above them in the report are
    skipped -- they'd be byte-identical to strategy A and add no signal."""
    candidates: list[ChunkCandidate] = []
    for p in report_passages_sorted:
        heading, heading_source_id = resolve_effective_heading(report_passages_sorted, p.passage_index)
        if not heading:
            continue
        members = [ChunkMember(p.id, ROLE_ANCHOR, 0)]
        if heading_source_id is not None:
            members.insert(0, ChunkMember(heading_source_id, ROLE_HEADING_CONTEXT, -1))
        candidates.append(
            ChunkCandidate(
                strategy=STRATEGY_HEADING_PLUS_PASSAGE,
                report_id=p.report_id,
                company_id=p.company_id,
                anchor_passage_id=p.id,
                text=f"Heading: {heading}\nContent: {p.text}",
                members=tuple(members),
                page_start=p.first_page_number,
                page_end=p.last_page_number,
            )
        )
    return candidates


def _with_heading(report_passages_sorted: Sequence[PassageRow], anchor: PassageRow) -> tuple[str, ChunkMember | None]:
    heading, heading_source_id = resolve_effective_heading(report_passages_sorted, anchor.passage_index)
    if not heading:
        return "", None
    return f"Heading: {heading}\n", (ChunkMember(heading_source_id, ROLE_HEADING_CONTEXT, -1) if heading_source_id else None)


def build_previous_plus_current_chunks(report_passages_sorted: Sequence[PassageRow]) -> list[ChunkCandidate]:
    """C: heading (where available) + previous passage + current passage."""
    candidates: list[ChunkCandidate] = []
    for p in report_passages_sorted:
        prev = _neighbor(report_passages_sorted, p.passage_index, -1)
        if prev is None:
            continue
        heading_prefix, heading_member = _with_heading(report_passages_sorted, p)
        members = [ChunkMember(prev.id, ROLE_PREVIOUS, 0), ChunkMember(p.id, ROLE_ANCHOR, 1)]
        if heading_member:
            members.insert(0, heading_member)
        candidates.append(
            ChunkCandidate(
                strategy=STRATEGY_PREVIOUS_PLUS_CURRENT,
                report_id=p.report_id,
                company_id=p.company_id,
                anchor_passage_id=p.id,
                text=f"{heading_prefix}{prev.text}\n\n{p.text}",
                members=tuple(members),
                page_start=min(prev.first_page_number, p.first_page_number),
                page_end=max(prev.last_page_number, p.last_page_number),
            )
        )
    return candidates


def build_current_plus_next_chunks(report_passages_sorted: Sequence[PassageRow]) -> list[ChunkCandidate]:
    """D: heading (where available) + current passage + next passage."""
    candidates: list[ChunkCandidate] = []
    for p in report_passages_sorted:
        nxt = _neighbor(report_passages_sorted, p.passage_index, 1)
        if nxt is None:
            continue
        heading_prefix, heading_member = _with_heading(report_passages_sorted, p)
        members = [ChunkMember(p.id, ROLE_ANCHOR, 0), ChunkMember(nxt.id, ROLE_NEXT, 1)]
        if heading_member:
            members.insert(0, heading_member)
        candidates.append(
            ChunkCandidate(
                strategy=STRATEGY_CURRENT_PLUS_NEXT,
                report_id=p.report_id,
                company_id=p.company_id,
                anchor_passage_id=p.id,
                text=f"{heading_prefix}{p.text}\n\n{nxt.text}",
                members=tuple(members),
                page_start=min(p.first_page_number, nxt.first_page_number),
                page_end=max(p.last_page_number, nxt.last_page_number),
            )
        )
    return candidates


def build_local_window_chunks(report_passages_sorted: Sequence[PassageRow]) -> list[ChunkCandidate]:
    """E: heading + previous + current + next. Requires both neighbors to
    exist -- interior passages only; boundary passages are already covered
    by C/D."""
    candidates: list[ChunkCandidate] = []
    for p in report_passages_sorted:
        prev = _neighbor(report_passages_sorted, p.passage_index, -1)
        nxt = _neighbor(report_passages_sorted, p.passage_index, 1)
        if prev is None or nxt is None:
            continue
        heading_prefix, heading_member = _with_heading(report_passages_sorted, p)
        members = [
            ChunkMember(prev.id, ROLE_PREVIOUS, 0),
            ChunkMember(p.id, ROLE_ANCHOR, 1),
            ChunkMember(nxt.id, ROLE_NEXT, 2),
        ]
        if heading_member:
            members.insert(0, heading_member)
        candidates.append(
            ChunkCandidate(
                strategy=STRATEGY_LOCAL_WINDOW,
                report_id=p.report_id,
                company_id=p.company_id,
                anchor_passage_id=p.id,
                text=f"{heading_prefix}{prev.text}\n\n{p.text}\n\n{nxt.text}",
                members=tuple(members),
                page_start=min(prev.first_page_number, p.first_page_number, nxt.first_page_number),
                page_end=max(prev.last_page_number, p.last_page_number, nxt.last_page_number),
            )
        )
    return candidates


def build_comparison_pair_chunks(comparisons: Iterable[ComparisonRow], passage_by_id: dict[uuid.UUID, PassageRow]) -> list[ChunkCandidate]:
    """H: earlier passage + later passage, explicitly labeled, for
    comparison-linked passage pairs where both sides are real (excludes
    NEW/REMOVED rows, which have only one side by definition). Anchor is the
    LATER side, matching the research-layer's role-symmetric convention
    where a report's passages act as query-like on the LATER side of a
    comparison (see `embedding_config.py` module docstring)."""
    candidates: list[ChunkCandidate] = []
    for c in comparisons:
        if c.earlier_passage_id is None or c.later_passage_id is None:
            continue
        if c.alignment_status not in _VALID_BOTH_SIDES_ALIGNMENT_STATUSES:
            continue
        earlier = passage_by_id.get(c.earlier_passage_id)
        later = passage_by_id.get(c.later_passage_id)
        if earlier is None or later is None:
            continue
        text = (
            f"Earlier report ({c.earlier_period_end or 'unknown period'}): {earlier.text}\n\n"
            f"Later report ({c.later_period_end or 'unknown period'}): {later.text}"
        )
        members = (
            ChunkMember(earlier.id, ROLE_EARLIER_SIDE, 0),
            ChunkMember(later.id, ROLE_LATER_SIDE, 1),
        )
        contexts = (
            ComparisonContext(c.id, c.report_comparison_id, "EARLIER", c.alignment_status, c.earlier_period_end, c.later_period_end),
            ComparisonContext(c.id, c.report_comparison_id, "LATER", c.alignment_status, c.earlier_period_end, c.later_period_end),
        )
        candidates.append(
            ChunkCandidate(
                strategy=STRATEGY_COMPARISON_PAIR,
                report_id=later.report_id,
                company_id=c.company_id,
                anchor_passage_id=later.id,
                text=text,
                members=members,
                page_start=min(earlier.first_page_number, later.first_page_number),
                page_end=max(earlier.last_page_number, later.last_page_number),
                comparison_contexts=contexts,
            )
        )
    return candidates


# ---------------------------------------------------------------------------
# F: fixed 256-token target / 64-token overlap window, spanning passage
# boundaries within one report (never crossing a report boundary). Built
# over whitespace-delimited words with a real tokenizer count function so
# windows never split a word and stay close to the target without a fixed
# word:token ratio assumption.
# ---------------------------------------------------------------------------

_WORD_PATTERN = re.compile(r"\S+")

_FIXED_WINDOW_TARGET_TOKENS = 256
_FIXED_WINDOW_OVERLAP_TOKENS = 64


def build_fixed_token_window_chunks(
    report_passages_sorted: Sequence[PassageRow], count_tokens: Callable[[str], int]
) -> list[ChunkCandidate]:
    """F: FIXED_TOKEN_WINDOW_256_64. `count_tokens` is the real pinned
    tokenizer's token counter (injected so this stays testable with a cheap
    fake in unit tests -- see `token_budget.py`'s identical injection
    pattern).

    Window boundaries are found via a per-word token-count cache and a
    prefix-sum array, not by re-tokenizing the whole growing window text at
    every candidate word -- the latter is O(words-per-window) real
    tokenizer calls per window (O(n^2) over a long report) and was measured
    to make a full-corpus build impractically slow. Per-word counts are a
    close approximation of a joined multi-word span's real count for this
    tokenizer; `token_budget.enforce_token_budget` re-measures and trims the
    final assembled text exactly before persistence, so any small
    approximation error here is corrected, never silently shipped.
    """
    if not report_passages_sorted:
        return []

    full_text_parts: list[str] = []
    passage_spans: list[tuple[PassageRow, int, int]] = []  # (passage, char_start, char_end) in full_text
    cursor = 0
    for i, p in enumerate(report_passages_sorted):
        if i > 0:
            full_text_parts.append(" ")
            cursor += 1
        start = cursor
        full_text_parts.append(p.text)
        cursor += len(p.text)
        passage_spans.append((p, start, cursor))
    full_text = "".join(full_text_parts)

    words = [(m.group(0), m.start(), m.end()) for m in _WORD_PATTERN.finditer(full_text)]
    if not words:
        return []

    word_token_cache: dict[str, int] = {}

    def word_tokens(word: str) -> int:
        cached = word_token_cache.get(word)
        if cached is not None:
            return cached
        # Subtract the fixed [CLS]/[SEP] special-token overhead so summed
        # per-word counts approximate a joined multi-word span's count, not
        # a sum of standalone single-word-plus-special-tokens counts.
        n = max(count_tokens(word) - 2, 1)
        word_token_cache[word] = n
        return n

    cumulative = [0] * (len(words) + 1)
    for idx, (w, _s, _e) in enumerate(words):
        cumulative[idx + 1] = cumulative[idx] + word_tokens(w)

    def covering_passages(char_start: int, char_end: int) -> list[PassageRow]:
        return [p for p, s, e in passage_spans if s < char_end and e > char_start]

    def midpoint_passage(char_start: int, char_end: int) -> PassageRow:
        mid = (char_start + char_end) // 2
        for p, s, e in passage_spans:
            if s <= mid < e:
                return p
        return passage_spans[-1][0]

    candidates: list[ChunkCandidate] = []
    i = 0
    n = len(words)
    while i < n:
        target = cumulative[i] + _FIXED_WINDOW_TARGET_TOKENS
        j = i + 1
        while j < n and cumulative[j] < target:
            j += 1
        j = min(j, n)
        char_start, char_end = words[i][1], words[j - 1][2]
        window_text = full_text[char_start:char_end]

        covered = covering_passages(char_start, char_end)
        if covered:
            anchor = midpoint_passage(char_start, char_end)
            members = [
                ChunkMember(p.id, ROLE_ANCHOR if p.id == anchor.id else ROLE_TOKEN_MEMBER, order)
                for order, p in enumerate(covered)
            ]
            candidates.append(
                ChunkCandidate(
                    strategy=STRATEGY_FIXED_TOKEN_WINDOW_256_64,
                    report_id=anchor.report_id,
                    company_id=anchor.company_id,
                    anchor_passage_id=anchor.id,
                    text=window_text,
                    members=tuple(members),
                    page_start=min(p.first_page_number for p in covered),
                    page_end=max(p.last_page_number for p in covered),
                )
            )

        if j >= n:
            break
        # Step back ~`_FIXED_WINDOW_OVERLAP_TOKENS` worth of approximate
        # tokens for the next window's start -- O(1) per step via the same
        # prefix-sum array, no tokenizer calls in this loop.
        overlap_target = cumulative[j] - _FIXED_WINDOW_OVERLAP_TOKENS
        overlap_start = j - 1
        while overlap_start > i and cumulative[overlap_start] > overlap_target:
            overlap_start -= 1
        i = max(overlap_start, i + 1)

    return candidates
