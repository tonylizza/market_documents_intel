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
CLASSIFICATION_RULES_VERSION = 1


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
