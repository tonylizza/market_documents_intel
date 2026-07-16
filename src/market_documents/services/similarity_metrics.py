"""Pure, independently testable lexical similarity metrics.

No database access and no dependency on the ORM -- every function here
takes plain strings/token lists and returns plain values, so they can be
unit tested without PostgreSQL.

All metrics follow the same convention: 1.0 means identical/highly similar,
0.0 means highly dissimilar, and `None` means the metric was explicitly
undefined or unfinite for these inputs (e.g. an empty token stream) -- never
a fabricated 0 or 1. Callers must handle `None` explicitly; it is a
diagnostic signal for `similarity_quality`, not an error to be swallowed.
"""

import difflib
import math
import time
from collections import Counter
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from market_documents.models.enums import DiffMode
from market_documents.services.similarity_config import SIMILARITY_CONFIG, SimilarityConfig
from market_documents.services.similarity_tokenization import bigrams, tokenize


def _clamp_unit(value: float) -> float | None:
    """Guard against float drift and non-finite results.

    Cosine similarity is mathematically bounded to [0, 1] for these inputs
    (both vectors are non-negative), but floating-point summation can push a
    value marginally outside that range (e.g. 1.0000000000000002). Anything
    genuinely non-finite (nan/inf) is treated as a failed calculation, not a
    valid-looking score.
    """
    if not math.isfinite(value):
        return None
    return max(0.0, min(1.0, value))


def lexical_cosine_similarity(
    tokens_a: list[str], tokens_b: list[str]
) -> float | None:
    """Pair-local sublinear-term-frequency cosine similarity.

    Builds a vocabulary from only the two token lists passed in (the union
    of their unique terms), so no corpus-wide fitting ever occurs and
    scoring one pair can never be affected by any other document in the
    corpus. For a raw term count c > 0, applies sublinear scaling
    `1 + log(c)`; a count of 0 stays 0. This is explicitly NOT TF-IDF -- no
    document-frequency or inverse-document-frequency weighting is computed
    anywhere.

    Returns `None` (not 0.0) when either document has zero tokens, since
    cosine similarity is undefined for a zero vector.
    """
    if not tokens_a or not tokens_b:
        return None

    vocab = sorted(set(tokens_a) | set(tokens_b))
    counts_a = Counter(tokens_a)
    counts_b = Counter(tokens_b)

    vec_a = [1.0 + math.log(counts_a[term]) if counts_a[term] > 0 else 0.0 for term in vocab]
    vec_b = [1.0 + math.log(counts_b[term]) if counts_b[term] > 0 else 0.0 for term in vocab]

    if vec_a == vec_b:
        # Same term-frequency vector -> cosine is exactly 1.0. Computed via
        # division below, float rounding in sqrt(dot)*sqrt(dot) can land a
        # hair under 1.0 (e.g. 0.9999999999999998) even for identical
        # inputs; short-circuit rather than let that leak into callers.
        return 1.0

    norm_a = math.sqrt(sum(v * v for v in vec_a))
    norm_b = math.sqrt(sum(v * v for v in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return None

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    # Equivalent to L2-normalizing both vectors first, then taking the dot
    # product -- avoids materializing the normalized vectors separately.
    return _clamp_unit(dot / (norm_a * norm_b))


def jaccard_similarity(
    tokens_a: list[str], tokens_b: list[str], shingle_size: int = 2
) -> float | None:
    """Jaccard similarity over word-shingle sets (default: bigrams).

    Shingles capture phrase-level overlap, distinct from the unigram
    cosine signal above. Duplicate shingles collapse naturally (sets), so
    repetition doesn't change the score. Returns `None` when both documents
    have fewer than `shingle_size` tokens (no shingles on either side, so
    the ratio is 0/0 -- explicitly undefined, not 0.0 or 1.0).
    """
    shingles_a = set(bigrams(tokens_a, shingle_size))
    shingles_b = set(bigrams(tokens_b, shingle_size))

    if not shingles_a and not shingles_b:
        return None

    union = shingles_a | shingles_b
    intersection = shingles_a & shingles_b
    return _clamp_unit(len(intersection) / len(union))


def diff_similarity(
    tokens_a: list[str], tokens_b: list[str], autojunk: bool = False
) -> float | None:
    """Normalized sequence-diff similarity over token sequences.

    Uses `difflib.SequenceMatcher` on token lists (not raw characters), so
    PDF line-wrapping or whitespace differences -- already normalized away
    by M2 cleaning and this module's tokenizer -- cannot dominate the
    result. `autojunk=False` by default: annual reports legitimately repeat
    common tokens ("the", "and", numbers) far more than difflib's 1%
    "popular element" heuristic tolerates, and treating those as junk would
    discard literal-reuse signal that matters for disclosure comparison.
    This is a syntactic contiguous-block-overlap measure (Ratcliff/
    Obershelp), not a semantic similarity measure.

    Returns `None` when both token sequences are empty (undefined, not
    difflib's native 1.0 for two empty sequences) for consistency with the
    other metrics' empty-input convention.
    """
    if not tokens_a and not tokens_b:
        return None
    matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=autojunk)
    return _clamp_unit(matcher.ratio())


@dataclass(frozen=True)
class DiffResult:
    value: float | None
    mode: DiffMode
    duration_ms: float | None


def diff_similarity_with_mode(
    tokens_a: list[str],
    tokens_b: list[str],
    *,
    token_threshold: int,
    autojunk: bool = False,
) -> DiffResult:
    """Token-count-bounded wrapper around `diff_similarity`.

    Above `token_threshold` (checked against either document), the exact
    SequenceMatcher computation is skipped entirely rather than silently
    switched to a faster-but-different-scoring mode: benchmarking on real
    ~50-85k-token report pairs showed autojunk=True runs ~7-9x faster but
    can shift the score by as much as 0.15, which is not a safe silent
    substitute for the same field name. A skip is recorded as
    DiffMode.SKIPPED_TOKEN_LIMIT with `value=None` -- never a fabricated
    score -- so quality/audit logic can distinguish "diff unavailable due
    to size" from "diff genuinely failed".
    """
    if len(tokens_a) > token_threshold or len(tokens_b) > token_threshold:
        return DiffResult(value=None, mode=DiffMode.SKIPPED_TOKEN_LIMIT, duration_ms=None)

    started = time.monotonic()
    value = diff_similarity(tokens_a, tokens_b, autojunk=autojunk)
    duration_ms = (time.monotonic() - started) * 1000.0
    mode = DiffMode.FULL_AUTOJUNK if autojunk else DiffMode.FULL_NO_AUTOJUNK
    return DiffResult(value=value, mode=mode, duration_ms=duration_ms)


def edit_similarity(tokens_a: list[str], tokens_b: list[str]) -> float | None:
    """Token-level normalized edit similarity (RapidFuzz Levenshtein).

    RapidFuzz's distance functions operate on arbitrary sequences of
    hashable objects, so this runs token-level rather than character-level,
    using a bit-parallel (Myers/Hyyroe) implementation that is roughly
    O(N*M/64) time and O(N) memory -- far cheaper than a naive O(N*M)
    dynamic-programming table, and safe on realistically sized annual
    reports (tens of thousands of tokens).

    Distinct from `diff_similarity`: SequenceMatcher finds longest
    contiguous matching blocks and can "recognize" a relocated block of
    text; Levenshtein counts minimum single-token insert/delete/substitute
    operations, so it penalizes reordering that diff can match as a moved
    block. Reporting both surfaces genuinely different signal.

    Returns `None` when both token sequences are empty, for the same reason
    as `diff_similarity` (RapidFuzz's native default for two empty
    sequences is 1.0, which is not this module's empty-input convention).
    """
    if not tokens_a and not tokens_b:
        return None
    return _clamp_unit(Levenshtein.normalized_similarity(tokens_a, tokens_b))


@dataclass(frozen=True)
class MetricSet:
    lexical_cosine_similarity: float | None
    jaccard_similarity: float | None
    diff_similarity: float | None
    diff_mode: DiffMode
    diff_duration_ms: float | None
    edit_similarity: float | None

    def values(self) -> list[float]:
        """Non-None similarity metric values, for disagreement/quality checks."""
        return [
            v
            for v in (
                self.lexical_cosine_similarity,
                self.jaccard_similarity,
                self.diff_similarity,
                self.edit_similarity,
            )
            if v is not None
        ]


def compute_metrics(
    earlier_text: str, later_text: str, config: SimilarityConfig = SIMILARITY_CONFIG
) -> MetricSet:
    """Tokenize both documents once and compute all four metrics from that."""
    tokens_a = tokenize(earlier_text)
    tokens_b = tokenize(later_text)
    diff_result = diff_similarity_with_mode(
        tokens_a, tokens_b, token_threshold=config.diff_token_threshold, autojunk=config.diff_autojunk
    )
    return MetricSet(
        lexical_cosine_similarity=lexical_cosine_similarity(tokens_a, tokens_b),
        jaccard_similarity=jaccard_similarity(tokens_a, tokens_b, config.jaccard_shingle_size),
        diff_similarity=diff_result.value,
        diff_mode=diff_result.mode,
        diff_duration_ms=diff_result.duration_ms,
        edit_similarity=edit_similarity(tokens_a, tokens_b),
    )


@dataclass(frozen=True)
class LengthChangeFeatures:
    earlier_word_count: int
    later_word_count: int
    word_count_change: int
    word_count_change_ratio: float | None
    earlier_character_count: int
    later_character_count: int
    character_count_change: int
    character_count_change_ratio: float | None


def compute_length_change_features(
    *,
    earlier_word_count: int,
    later_word_count: int,
    earlier_character_count: int,
    later_character_count: int,
) -> LengthChangeFeatures:
    """Transparent document-size change features.

    Ratios are `None` (not a fabricated inf or 0) when the earlier-report
    denominator is zero. Length change is a diagnostic feature, never a
    stand-in for document similarity.
    """
    word_count_change = later_word_count - earlier_word_count
    word_count_change_ratio = (
        word_count_change / earlier_word_count if earlier_word_count else None
    )
    character_count_change = later_character_count - earlier_character_count
    character_count_change_ratio = (
        character_count_change / earlier_character_count if earlier_character_count else None
    )
    return LengthChangeFeatures(
        earlier_word_count=earlier_word_count,
        later_word_count=later_word_count,
        word_count_change=word_count_change,
        word_count_change_ratio=word_count_change_ratio,
        earlier_character_count=earlier_character_count,
        later_character_count=later_character_count,
        character_count_change=character_count_change,
        character_count_change_ratio=character_count_change_ratio,
    )
