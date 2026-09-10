"""Retrieval-subchunk construction for oversized passages (Milestone 6).

Splits one canonical `Passage.raw_text` -- already confirmed to exceed the
embedding model's token limit -- into deterministic, token-safe,
sentence-aware chunks for embedding. This is a candidate-generation-only
mechanism: the canonical passage itself never changes shape, and a chunk
never becomes a user-facing passage, an alignable unit, or a scoring input
in its own right (see `alignment_candidates.py`/`passage_alignment.py` and
`docs/oversized-passage-retrieval-subchunks-experiment.md`).

Pure, no DB/session, independently unit-testable like `passage_segmentation
.segment_blocks` -- `count_tokens` is injected so real-corpus behavior uses
the pinned BGE tokenizer (`passage_embedding.EmbeddingModel.count_tokens`)
while tests can use a fake with a controllable token/word ratio.

Chunking policy: deterministic sentence-boundary greedy packing under
`RetrievalChunkConfig.max_tokens`, falling back to a word-boundary split
only for the (unobserved in the real corpus, per
`docs/embedding-eligibility-token-limit-diagnostic.md` Section 11) case of
one sentence alone exceeding the ceiling. No overlap between consecutive
chunks (see `retrieval_chunk_config.py` for the rationale on both).
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Callable

from market_documents.services.retrieval_chunk_config import RETRIEVAL_CHUNK_CONFIG, RetrievalChunkConfig

_SENTENCE_END = re.compile(r"[.!?;](?=\s|$)")
_WORD = re.compile(r"\S+\s*")


@dataclass(frozen=True)
class RetrievalChunk:
    chunk_index: int
    text: str
    char_start: int
    char_end: int
    token_count: int
    content_hash: str


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """Contiguous, gapless spans tiling `[0, len(text))` exactly -- mirrors
    `passage_segmentation._sentence_spans` (kept as a separate copy since
    this module operates on token budgets via an injected tokenizer, not
    word counts, and must remain independently versioned/testable)."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        while end < len(text) and text[end].isspace():
            end += 1
        if end > start:
            spans.append((start, end))
            start = end
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _word_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans = [(start + m.start(), start + m.end()) for m in _WORD.finditer(text[start:end])]
    return spans or [(start, end)]


def _pack_spans(
    text: str,
    spans: list[tuple[int, int]],
    max_tokens: int,
    count_tokens: Callable[[str], int],
    finer: Callable[[str, int, int, int, Callable[[str], int]], list[tuple[int, int]]] | None,
) -> list[tuple[int, int]]:
    """Greedily pack contiguous, gapless spans into pieces whose *tokenized*
    length is at most `max_tokens`, recursively subdividing (via `finer`)
    any single span that alone already exceeds the ceiling."""
    pieces: list[tuple[int, int]] = []
    cur_start: int | None = None
    cur_end: int | None = None
    cur_tokens = 0
    for span_start, span_end in spans:
        seg_tokens = count_tokens(text[span_start:span_end])
        if seg_tokens > max_tokens and finer is not None:
            if cur_start is not None:
                pieces.append((cur_start, cur_end))
                cur_start, cur_tokens = None, 0
            pieces.extend(finer(text, span_start, span_end, max_tokens, count_tokens))
            continue
        if cur_start is not None:
            combined_tokens = count_tokens(text[cur_start:span_end])
            if combined_tokens > max_tokens:
                pieces.append((cur_start, cur_end))
                cur_start, cur_end, cur_tokens = span_start, span_end, seg_tokens
            else:
                cur_end = span_end
                cur_tokens = combined_tokens
        else:
            cur_start, cur_end, cur_tokens = span_start, span_end, seg_tokens
    if cur_start is not None:
        pieces.append((cur_start, cur_end))
    return pieces


def _word_fallback(
    text: str, start: int, end: int, max_tokens: int, count_tokens: Callable[[str], int]
) -> list[tuple[int, int]]:
    return _pack_spans(text, _word_spans(text, start, end), max_tokens, count_tokens, finer=None)


def split_into_retrieval_chunks(
    text: str,
    *,
    count_tokens: Callable[[str], int],
    config: RetrievalChunkConfig = RETRIEVAL_CHUNK_CONFIG,
) -> list[RetrievalChunk]:
    """Split `text` into deterministic, token-safe retrieval chunks.

    `count_tokens` must be the real embedding-model tokenizer (matching the
    `>MAXIMUM_MODEL_TOKENS` skip check this function exists to resolve) --
    word count alone is exactly the calibration gap this milestone's
    diagnostic found (see `docs/embedding-eligibility-token-limit-diagnostic
    .md` Section 4.2), so it must never be used as a proxy here.
    """
    spans = _pack_spans(text, _sentence_spans(text), config.max_tokens, count_tokens, finer=_word_fallback)
    chunks: list[RetrievalChunk] = []
    for index, (start, end) in enumerate(spans):
        chunk_text = text[start:end].strip()
        chunks.append(
            RetrievalChunk(
                chunk_index=index,
                text=chunk_text,
                char_start=start,
                char_end=end,
                token_count=count_tokens(chunk_text),
                content_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
            )
        )
    return chunks
