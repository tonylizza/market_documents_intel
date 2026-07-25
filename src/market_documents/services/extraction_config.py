"""Centralized, versioned extraction thresholds.

These values are analysis parameters, not per-deployment operational
settings: they must be identical across environments for the extraction
configuration fingerprint (see `compute_configuration_hash`) to mean
anything, so they deliberately live here as typed constants rather than in
`.env`. Bump the relevant `*_VERSION` constant whenever a heuristic or
threshold changes -- that is what forces a fresh `ExtractionRun` instead of
silently reusing a stale one.
"""

import hashlib
import json
from dataclasses import asdict, dataclass

EXTRACTOR_NAME = "pymupdf"

CLEANING_RULES_VERSION = 1
QUALITY_THRESHOLDS_VERSION = 1
CLASSIFICATION_RULES_VERSION = 3


@dataclass(frozen=True)
class ExtractionConfig:
    # Page-level usability
    min_chars_for_usable_page: int = 40
    min_alpha_ratio: float = 0.5

    # Header/footer detection
    top_region_fraction: float = 0.12
    bottom_region_fraction: float = 0.10
    header_footer_repetition_threshold: float = 0.6
    header_footer_min_page_count: int = 5

    # Block classification
    heading_max_words: int = 12
    numeric_fragment_max_words: int = 8
    numeric_fragment_min_digit_ratio: float = 0.5
    table_like_min_digit_ratio: float = 0.3
    table_like_min_numeric_tokens: int = 3
    decorative_max_words: int = 3
    max_numeric_density_for_narrative: float = 0.35

    # Dense multi-line table rows whose label text dilutes the whole-block
    # digit ratio below `table_like_min_digit_ratio` (e.g. a row like
    # "Semi-skilled and discretionary decision-making 247 20 1 4 310 29 10
    # 35 656", digit_ratio ~=0.28) are still recognizable by line structure:
    # many short lines -- one PDF text line per table cell -- packed into a
    # block. `table_like_dense_line_density_threshold` is lines per point of
    # bbox height; ordinary running text tops out around 0.1-0.15 even in
    # tight paragraphs (corpus p95 = 0.34, but that tail is itself mostly
    # this same table-row phenomenon -- see block_diagnostics audit).
    table_like_dense_line_density_threshold: float = 0.25
    table_like_dense_min_digit_ratio: float = 0.15

    # Corruption signature for overlapping/duplicated PDF text objects (e.g.
    # a cover-page wordmark rendered as dozens of overlapping partial-word
    # spans): real distinct lines cannot physically pack denser than roughly
    # 1 line per 4-5pt of height, so a block whose line count per point of
    # bbox height exceeds this is not prose at all, regardless of word
    # count. Calibrated from the reference corpus: p99.99 line density
    # across 93,818 real blocks was 1.83; the one confirmed corruption case
    # measured 42.7 -- more than an order of magnitude beyond the threshold,
    # so this has no observed false-positive risk on real content.
    overlapping_text_line_density_threshold: float = 2.0

    # Report-level quality rollup
    low_text_page_tolerance: float = 0.20
    max_empty_page_ratio: float = 0.05
    good_quality_usable_page_threshold: float = 0.95
    usable_quality_usable_page_threshold: float = 0.80
    needs_review_usable_page_threshold: float = 0.40


EXTRACTION_CONFIG = ExtractionConfig()


def compute_configuration_hash(extractor_version: str, config: ExtractionConfig = EXTRACTION_CONFIG) -> str:
    """Deterministic fingerprint of everything that can change extraction output.

    An identical fingerprint means: same extractor, same extractor version,
    same cleaning/classification/quality rule versions, same thresholds.
    Any change to those inputs produces a different hash, which is what
    triggers a fresh `ExtractionRun` instead of a skip.
    """
    payload = {
        "extractor_name": EXTRACTOR_NAME,
        "extractor_version": extractor_version,
        "cleaning_rules_version": CLEANING_RULES_VERSION,
        "quality_thresholds_version": QUALITY_THRESHOLDS_VERSION,
        "classification_rules_version": CLASSIFICATION_RULES_VERSION,
        "config": asdict(config),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
