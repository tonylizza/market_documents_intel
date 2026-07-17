"""Centralized, versioned disclosure-change feature thresholds, weights, and
configuration.

Mirrors `alignment_config.py`/`similarity_config.py`/`passage_config.py`:
these are analysis parameters, not per-deployment settings, so they live
here as typed constants rather than in `.env`. Bump the relevant
`*_VERSION` constant whenever a weight, threshold, or formula changes --
that is what forces a fresh `FeatureRun` instead of silently reusing a
stale one.

Weights and thresholds below are provisional, set from first principles
(not tuned against market outcomes, per the milestone's explicit
prohibition) and are expected to be revised after inspecting real feature
results on the corpus.
"""

import hashlib
import json
from dataclasses import asdict, dataclass

ALGORITHM_VERSION = "1.0.0"
FEATURE_VERSION = "1.0.0"

LOW_INFORMATION_RULE_VERSION = 1
SCORE_FORMULA_VERSION = 1
QUALITY_THRESHOLDS_VERSION = 1
GAP_POLICY_VERSION = 1


@dataclass(frozen=True)
class FeatureConfig:
    # --- Low-information / heading-fragment diagnostics ---
    # A passage below this word count is "low-information" regardless of
    # type. This is deliberately a higher, feature-local threshold than
    # PassageConfig.min_words_hard_floor (15): the M4 hard floor already
    # excludes unusably tiny passages from alignment entirely, but many
    # heading-driven passages clear that floor while still being too short
    # to carry independent disclosure-change signal.
    minimum_feature_passage_words: int = 40
    # When False (default), low-information passages -- and, as a subset,
    # HEADING_WITH_BODY passages below the same threshold -- are excluded
    # from feature-eligible aggregates. All-passage aggregates always
    # include them regardless of these flags.
    include_heading_only_passages: bool = False
    include_low_information_passages: bool = False

    # --- Composite disclosure-change score weights (word-weighted rates) ---
    # unchanged contributes 0 implicitly (present in the rate denominator,
    # absent from the numerator) -- see feature_metrics.compute_disclosure_change_score.
    unchanged_weight: float = 0.0
    lightly_modified_weight: float = 0.25
    substantially_modified_weight: float = 0.65
    new_weight: float = 0.85
    removed_weight: float = 0.85
    ambiguous_weight: float = 0.5

    # --- Coverage floors gating score availability and primary eligibility ---
    minimum_alignment_coverage: float = 0.80
    minimum_embedding_coverage: float = 0.80

    # --- Quality thresholds ---
    # Share (by word) of the feature-eligible population classified
    # AMBIGUOUS, above which the result is NEEDS_REVIEW.
    ambiguous_word_share_threshold: float = 0.15
    # Share (by count) of aligned rows at LOW or NEEDS_REVIEW confidence,
    # above which the result is NEEDS_REVIEW.
    low_confidence_share_threshold: float = 0.25

    # --- Reporting-gap policy ---
    # A pair's gap_months outside [primary_gap_months_min, primary_gap_months_max]
    # is `irregular_gap=True`. A transition-flagged pair (ReportPair.is_transition)
    # commonly falls outside this window by design and is not quality-penalized
    # for it (approved transition handling), but is still excluded from primary
    # annual ranking, same as any other irregular-gap pair.
    primary_gap_months_min: int = 9
    primary_gap_months_max: int = 15


FEATURE_CONFIG = FeatureConfig()


def compute_configuration_hash(config: FeatureConfig = FEATURE_CONFIG) -> str:
    """Deterministic fingerprint of everything that can change feature output.

    An identical fingerprint means: same algorithm/feature version, same
    per-rule version, same thresholds/weights. Any change to those inputs
    produces a different hash, which is what triggers a fresh `FeatureRun`
    instead of a skip.
    """
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "feature_version": FEATURE_VERSION,
        "low_information_rule_version": LOW_INFORMATION_RULE_VERSION,
        "score_formula_version": SCORE_FORMULA_VERSION,
        "quality_thresholds_version": QUALITY_THRESHOLDS_VERSION,
        "gap_policy_version": GAP_POLICY_VERSION,
        "config": asdict(config),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
