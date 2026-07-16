"""Centralized, versioned similarity-scoring thresholds and configuration.

Mirrors `extraction_config.py`: these are analysis parameters, not
per-deployment settings, so they live here as typed constants rather than in
`.env`. Bump the relevant `*_VERSION` constant whenever a metric,
tokenization rule, or quality threshold changes -- that is what forces a
fresh `SimilarityRun` instead of silently reusing a stale one.
"""

import hashlib
import importlib.metadata
import json
from dataclasses import asdict, dataclass

from market_documents.services.similarity_tokenization import TOKENIZER_VERSION

ALGORITHM_VERSION = "1.0.0"

COSINE_CONFIG_VERSION = 1
JACCARD_CONFIG_VERSION = 1
# Bumped 1 -> 2 for the token-threshold bounding policy (M3.5): identical
# earlier configuration hashes must not be treated as equivalent to the
# new bounded behavior, so this forces a fresh SimilarityRun.
DIFF_CONFIG_VERSION = 2
EDIT_CONFIG_VERSION = 1
QUALITY_THRESHOLDS_VERSION = 1


@dataclass(frozen=True)
class SimilarityConfig:
    # Lexical cosine similarity (pair-local, sublinear term frequency, no IDF)
    cosine_ngram_range: tuple[int, int] = (1, 1)
    cosine_sublinear_tf: bool = True
    cosine_use_idf: bool = False
    cosine_normalization: str = "l2"

    # Jaccard similarity (word-shingle sets)
    jaccard_shingle_size: int = 2

    # Diff similarity (token-sequence difflib.SequenceMatcher)
    diff_autojunk: bool = False
    # Above this token count (either document), diff_similarity is skipped
    # entirely (DiffMode.SKIPPED_TOKEN_LIMIT) rather than computed with
    # autojunk=True: benchmarking on real ~50-85k-token report pairs showed
    # autojunk=True runs ~7-9x faster but shifts the score unpredictably
    # (delta up to 0.15 observed) -- not a safe silent substitute. 100,000
    # is comfortably above the current real-corpus max (84,709 tokens).
    diff_token_threshold: int = 100_000

    # Edit similarity (token-level RapidFuzz Levenshtein)
    edit_algorithm: str = "levenshtein_token"

    # Quality/review thresholds
    min_words_for_review: int = 200
    max_length_ratio_for_review: float = 3.0
    max_gap_months_for_review: int = 18
    metric_disagreement_threshold: float = 0.4


SIMILARITY_CONFIG = SimilarityConfig()


def _rapidfuzz_version() -> str:
    try:
        return importlib.metadata.version("rapidfuzz")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def compute_configuration_hash(config: SimilarityConfig = SIMILARITY_CONFIG) -> str:
    """Deterministic fingerprint of everything that can change similarity output.

    An identical fingerprint means: same algorithm version, same tokenizer
    version, same per-metric config-version, same thresholds, same RapidFuzz
    version. Any change to those inputs produces a different hash, which is
    what triggers a fresh `SimilarityRun` instead of a skip.
    """
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "tokenizer_version": TOKENIZER_VERSION,
        "cosine_config_version": COSINE_CONFIG_VERSION,
        "jaccard_config_version": JACCARD_CONFIG_VERSION,
        "diff_config_version": DIFF_CONFIG_VERSION,
        "edit_config_version": EDIT_CONFIG_VERSION,
        "quality_thresholds_version": QUALITY_THRESHOLDS_VERSION,
        "rapidfuzz_version": _rapidfuzz_version(),
        "config": asdict(config),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
