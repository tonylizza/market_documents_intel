"""Milestone 7B.2: standard-RAG Q&A chunk construction.

Deliberately a single, standard chunking policy -- not the Milestone 7B.1d
`qa_experiment` package's six-strategy research design (that experiment
concluded NOT READY against its own research thresholds; the 7B.2 brief is
explicit that this is an implementation milestone, not another research
gate). This module borrows the *algorithms* proven out by that spike
(fixed-token windowing with an injected tokenizer, nearest-heading
resolution, sentence-boundary-preferring trim with a word-level fallback for
punctuation-free financial/table text) but not its multi-strategy
`ChunkCandidate`/role-taxonomy machinery -- there is exactly one shape of
chunk here.

Pure and database-free, like `retrieval_contexts.py`/`labels.py`: no
function in this module ever opens a session. `publisher.py` is the only
caller, feeding it one report's ordered passages at a time (never crossing a
report boundary is therefore a call-site invariant, not something this
module has to detect).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

# Brief: target ~350 tokens, configurable within 300-400; ~70-token overlap,
# configurable within 60-80. Same 512-token hard ceiling as canonical
# passages (`services.embedding_config.MAXIMUM_MODEL_TOKENS`) -- imported
# lazily by callers rather than here, to keep this module free of any
# research/services dependency the way `retrieval_contexts.py` is.
DEFAULT_TARGET_TOKENS = 350
MINIMUM_TARGET_TOKENS = 300
MAXIMUM_TARGET_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 70
MINIMUM_OVERLAP_TOKENS = 60
MAXIMUM_OVERLAP_TOKENS = 80

_WORD_PATTERN = re.compile(r"\S+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
# How far past the raw token-count window boundary we're willing to look for
# a sentence-ending punctuation mark before giving up and cutting on a word
# boundary instead -- financial/table-like text often has no `.!?` at all
# (see `_word_trim_from_end`), so this is a preference, never a requirement.
_SENTENCE_SEARCH_TOLERANCE_CHARS = 240


@dataclass(frozen=True)
class QaPassageRow:
    """One `app.passages` row (or the pre-publish equivalent), ordered
    within its report by `passage_index`."""

    id: uuid.UUID
    report_id: uuid.UUID
    company_id: uuid.UUID
    passage_index: int
    heading: str | None
    text: str
    first_page_number: int
    last_page_number: int


@dataclass
class QaChunkCandidate:
    """Mutable during token-budget enforcement; one row per candidate, no
    strategy/role taxonomy -- every chunk has exactly the same shape."""

    report_id: uuid.UUID
    company_id: uuid.UUID
    chunk_index: int
    text: str
    section_heading: str | None
    page_start: int
    page_end: int
    member_passage_ids: tuple[uuid.UUID, ...]
    token_count: int
    truncation_policy: str = "none"


def resolve_effective_heading(
    report_passages_sorted: Sequence[QaPassageRow], target_index: int
) -> str | None:
    """Nearest resolvable heading for `target_index`, walking backward
    within the same report -- mirrors the research-layer segmentation rule
    where `heading_text` is only stamped on the first passage of a
    heading-started run."""
    for i, p in enumerate(report_passages_sorted):
        if p.passage_index == target_index:
            if p.heading:
                return p.heading
            for prior in reversed(report_passages_sorted[:i]):
                if prior.heading:
                    return prior.heading
            return None
    return None


def _word_trim_from_end(text: str, count_tokens: Callable[[str], int], budget: int) -> str:
    words = text.split()
    while len(words) > 1 and count_tokens(" ".join(words)) > budget:
        words = words[:-1]
    return " ".join(words)


def _sentence_trim_from_end(text: str, count_tokens: Callable[[str], int], budget: int) -> str:
    sentences = _SENTENCE_SPLIT.split(text)
    while len(sentences) > 1 and count_tokens(" ".join(sentences)) > budget:
        sentences = sentences[:-1]
    reduced = " ".join(sentences)
    if count_tokens(reduced) > budget:
        reduced = _word_trim_from_end(reduced, count_tokens, budget)
    return reduced


def _validate_bounds(target_tokens: int, overlap_tokens: int) -> None:
    if not (MINIMUM_TARGET_TOKENS <= target_tokens <= MAXIMUM_TARGET_TOKENS):
        raise ValueError(
            f"target_tokens={target_tokens} outside configured range "
            f"[{MINIMUM_TARGET_TOKENS}, {MAXIMUM_TARGET_TOKENS}]"
        )
    if not (MINIMUM_OVERLAP_TOKENS <= overlap_tokens <= MAXIMUM_OVERLAP_TOKENS):
        raise ValueError(
            f"overlap_tokens={overlap_tokens} outside configured range "
            f"[{MINIMUM_OVERLAP_TOKENS}, {MAXIMUM_OVERLAP_TOKENS}]"
        )
    # No explicit overlap_tokens < target_tokens check: MAXIMUM_OVERLAP_TOKENS
    # (80) is already smaller than MINIMUM_TARGET_TOKENS (300), so the two
    # range checks above make that invariant unconditionally true.


def _snap_to_sentence_boundary(full_text: str, char_start: int, raw_char_end: int, hard_char_end: int) -> int:
    """Prefer ending the window at a sentence boundary (`.!?` followed by
    whitespace) within `_SENTENCE_SEARCH_TOLERANCE_CHARS` of the raw
    token-count boundary, without ever reading past `hard_char_end` (the
    next word's end -- we never invent text). Falls back to `raw_char_end`
    (a plain word-boundary cut) when no in-range sentence end exists, which
    is common for table-like/numeric passages with no `.!?` at all."""
    search_end = min(hard_char_end, raw_char_end + _SENTENCE_SEARCH_TOLERANCE_CHARS)
    window = full_text[char_start:search_end]
    best = -1
    for match in re.finditer(r"[.!?](?=\s|$)", window):
        candidate_end = char_start + match.end()
        if candidate_end <= raw_char_end + _SENTENCE_SEARCH_TOLERANCE_CHARS:
            best = candidate_end
    if best == -1:
        return raw_char_end
    return max(best, char_start + 1)


def build_qa_chunks(
    report_passages_sorted: Sequence[QaPassageRow],
    count_tokens: Callable[[str], int],
    target_tokens: int = DEFAULT_TARGET_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    max_tokens: int = 512,
) -> list[QaChunkCandidate]:
    """Build overlapping, heading-prefixed chunks for one report's ordered
    passages. Never crosses a report boundary (the caller supplies exactly
    one report's passages); prefers sentence/paragraph boundaries over raw
    token-count cuts; retains page lineage via the passages a chunk's
    character span overlaps; deterministic given the same input (no
    randomness, no wall-clock dependence).
    """
    _validate_bounds(target_tokens, overlap_tokens)
    if not report_passages_sorted:
        return []

    full_text_parts: list[str] = []
    passage_spans: list[tuple[QaPassageRow, int, int]] = []
    cursor = 0
    for i, p in enumerate(report_passages_sorted):
        if i > 0:
            full_text_parts.append("\n\n")
            cursor += 2
        start = cursor
        full_text_parts.append(p.text)
        cursor += len(p.text)
        passage_spans.append((p, start, cursor))
    full_text = "".join(full_text_parts)

    words = [(m.start(), m.end()) for m in _WORD_PATTERN.finditer(full_text)]
    if not words:
        return []

    word_token_cache: dict[str, int] = {}

    def word_tokens(word: str) -> int:
        cached = word_token_cache.get(word)
        if cached is not None:
            return cached
        # Subtract the fixed [CLS]/[SEP] special-token overhead so summed
        # per-word counts approximate a joined multi-word span's count.
        n = max(count_tokens(word) - 2, 1)
        word_token_cache[word] = n
        return n

    cumulative = [0] * (len(words) + 1)
    for idx, (s, e) in enumerate(words):
        cumulative[idx + 1] = cumulative[idx] + word_tokens(full_text[s:e])

    def covering_passages(char_start: int, char_end: int) -> list[QaPassageRow]:
        return [p for p, s, e in passage_spans if s < char_end and e > char_start]

    def anchor_passage(char_start: int, char_end: int) -> QaPassageRow:
        mid = (char_start + char_end) // 2
        for p, s, e in passage_spans:
            if s <= mid < e:
                return p
        return passage_spans[-1][0]

    candidates: list[QaChunkCandidate] = []
    i = 0
    n = len(words)
    chunk_index = 0
    while i < n:
        target = cumulative[i] + target_tokens
        j = i + 1
        while j < n and cumulative[j] < target:
            j += 1
        j = min(j, n)

        char_start = words[i][0]
        raw_char_end = words[j - 1][1]
        hard_char_end = words[min(j, n - 1)][1]
        char_end = _snap_to_sentence_boundary(full_text, char_start, raw_char_end, hard_char_end)
        window_text = full_text[char_start:char_end].strip()

        if window_text:
            covered = covering_passages(char_start, char_end)
            if covered:
                anchor = anchor_passage(char_start, char_end)
                heading = resolve_effective_heading(report_passages_sorted, anchor.passage_index)
                text = f"Heading: {heading}\n{window_text}" if heading else window_text
                token_count = count_tokens(text)
                truncation_policy = "none"
                if token_count > max_tokens:
                    text = _sentence_trim_from_end(text, count_tokens, max_tokens)
                    token_count = count_tokens(text)
                    truncation_policy = "window_trimmed"
                candidates.append(
                    QaChunkCandidate(
                        report_id=anchor.report_id,
                        company_id=anchor.company_id,
                        chunk_index=chunk_index,
                        text=text,
                        section_heading=heading,
                        page_start=min(p.first_page_number for p in covered),
                        page_end=max(p.last_page_number for p in covered),
                        member_passage_ids=tuple(p.id for p in covered),
                        token_count=token_count,
                        truncation_policy=truncation_policy,
                    )
                )
                chunk_index += 1

        if j >= n:
            break
        # Step back ~overlap_tokens for the next window's start, using the
        # boundary actually used for *this* window's end (word-index `j`)
        # regardless of the sentence-boundary snap, so consecutive windows
        # keep a consistent approximate overlap.
        overlap_target = cumulative[j] - overlap_tokens
        overlap_start = j - 1
        while overlap_start > i and cumulative[overlap_start] > overlap_target:
            overlap_start -= 1
        i = max(overlap_start, i + 1)

    return candidates
