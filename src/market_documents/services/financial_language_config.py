"""Centralized, versioned financial-language-signal thresholds, weights, and
configuration.

Mirrors `feature_config.py`: these are analysis parameters, not
per-deployment settings, so they live here as typed constants. Bump the
relevant `*_VERSION` constant whenever a rule or formula changes -- that is
what forces a fresh `LanguageSignalRun` instead of silently reusing a stale
one. Every input the milestone brief calls out as hash-relevant (dictionary
identity/hash, term normalization, phrase behavior, inflection rules,
negation window/boundaries, structured-content population rules, list/table-
context inclusion, confidence filters, rate denominator, derived-signal
formulas, signal version) is folded into `compute_configuration_hash`.
"""

import hashlib
import json
from dataclasses import asdict, dataclass

from market_documents.services.similarity_tokenization import TOKENIZER_VERSION
from market_documents.services.structured_content_audit import STRUCTURED_CONTENT_RULE_VERSION

ALGORITHM_VERSION = "1.1.0"
SIGNAL_VERSION = "1.0.0"

# Loughran-McDonald sentiment categories -- typed columns on
# `PassageLanguageSignal`/`ReportPairLanguageFeatures` (spec item: "Core
# categories should be typed columns").
CORE_CATEGORIES = ("positive", "negative", "uncertainty", "litigious", "constraining", "strong_modal", "weak_modal")

# Custom domain taxonomy top-level categories (see
# config/financial_language_custom_taxonomy.yaml for the term lists).
CUSTOM_TAXONOMY_CATEGORIES = ("risk", "financial_condition", "governance", "strategy")

FINANCIAL_TOKENIZATION_VERSION = 1
PHRASE_MATCHING_VERSION = 1
INFLECTION_RULE_VERSION = 1
NEGATION_RULE_VERSION = 1
# Bumped for the Milestone 6 recalibration: `assess_language_quality`'s
# single blended gate was replaced by independent report-side/alignment-
# change assessments (`financial_language_quality.py`) -- a materially
# different quality computation, so historical runs must not be treated as
# equivalent to a fresh one under the old thresholds.
QUALITY_THRESHOLDS_VERSION = 2
# Governs which independent-eligibility rules apply
# (`report_side_primary_eligible` / `alignment_change_primary_eligible` vs.
# the deprecated single `primary_eligible`) -- see `financial_language_
# quality.py` module docstring.
ELIGIBILITY_POLICY_VERSION = 1
# Governs `assess_report_side_quality`'s specific thresholds/logic.
REPORT_SIDE_QUALITY_POLICY_VERSION = 1
# Governs `assess_alignment_change_quality`'s specific thresholds/logic.
ALIGNMENT_CHANGE_QUALITY_POLICY_VERSION = 1


@dataclass(frozen=True)
class FinancialLanguageConfig:
    # --- Negation ---
    # Maximum tokens a negator's scope extends forward before it stops
    # counting as negating a later hit, even absent punctuation/conjunction.
    negation_window: int = 5
    negation_boundary_conjunctions: tuple[str, ...] = ("but", "however", "although", "though", "yet")

    # --- Rate denominator ---
    rate_denominator_words: int = 1000

    # --- Population / coverage thresholds (shared by both quality layers) ---
    # Share of a report side's all_passages words that made it into the
    # primary_narrative population, below which the result needs review.
    minimum_primary_narrative_word_coverage: float = 0.70
    # Share (by word) of the primary-narrative population classified
    # AMBIGUOUS, above which the result is NEEDS_REVIEW -- same semantics
    # and default as `FeatureConfig.ambiguous_word_share_threshold`. Applies
    # to *alignment-change* quality only (AMBIGUOUS rows are still included
    # in report-side totals; see `financial_language_quality.py`).
    ambiguous_word_share_threshold: float = 0.15

    # --- Dictionary coverage (Milestone 6 recalibration, Phase 7/11) ---
    # Replaces the provisional flat 0.05 hard-eligibility cutoff. Evidence:
    # the post-Loughran-McDonald-import corpus (25 pairs, 6 companies) has a
    # per-side primary-narrative match rate ranging 0.043-0.069 (median
    # ~0.056); only KP2's five pairs (0.043-0.050) sit under 0.05. No pair in
    # this corpus is anywhere near zero. Three explicit bands, evidence-
    # calibrated rather than chosen to make every pair pass:
    #   < dictionary_match_rate_anomalous_threshold        -> NEEDS_REVIEW
    #     ("unusually low match rate" / zero matches -- well below anything
    #     observed even for KP2, so this would indicate a real dictionary/
    #     matching problem, not ordinary variation).
    #   [anomalous, dictionary_match_rate_borderline_threshold) -> WARNING
    #     (informational only -- "borderline but plausible", e.g. KP2).
    #   >= borderline_threshold                             -> no penalty
    #     ("ordinary observed coverage").
    # A dictionary that is entirely unavailable/unimported is a separate,
    # harder failure handled upstream by `LanguageSignalNotEligibleError`
    # (`select_language_signal_source`), never reached here.
    dictionary_match_rate_anomalous_threshold: float = 0.02
    dictionary_match_rate_borderline_threshold: float = 0.05

    # --- Alignment-change-specific thresholds (Milestone 6 recalibration) ---
    # Share (by word, alignment-eligible population) whose accepted
    # correspondence was flagged non-unique by `detect_candidate_collisions`
    # (duplicate/boilerplate content -- see `classify_collision`). Observed
    # corpus range is 0.354-0.886 (median ~0.634): collision is the corpus's
    # normal condition (repeated statutory/boilerplate disclosure), not an
    # error, so the WARNING band starts near the observed median and only
    # the genuine right-tail outlier (this corpus's max, 0.886) crosses into
    # NEEDS_REVIEW.
    collision_flagged_word_share_warning_threshold: float = 0.60
    collision_flagged_word_share_needs_review_threshold: float = 0.85
    # Share (by word) with no alignment counterpart at all (NEW + REMOVED)
    # -- informational only (high content turnover is a legitimate report
    # characteristic, not evidence of a bad match); observed range is
    # 0.024-0.484.
    unmatched_word_share_warning_threshold: float = 0.40


FINANCIAL_LANGUAGE_CONFIG = FinancialLanguageConfig()


@dataclass(frozen=True)
class DictionaryFingerprint:
    """DB-free projection of the dictionaries actually used by a run, so this
    module never needs an ORM session just to compute a hash."""

    name: str
    version: str
    source_hash: str


def compute_configuration_hash(
    dictionaries: tuple[DictionaryFingerprint, ...], config: FinancialLanguageConfig = FINANCIAL_LANGUAGE_CONFIG
) -> str:
    """Deterministic fingerprint of everything that can change language-
    signal output. Identical fingerprint means: same dictionaries (by name/
    version/file hash), same tokenization/phrase/inflection/negation rule
    versions, same structured-content classifier version, same thresholds.
    Any change triggers a fresh `LanguageSignalRun` instead of a skip.
    """
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "signal_version": SIGNAL_VERSION,
        "base_tokenizer_version": TOKENIZER_VERSION,
        "financial_tokenization_version": FINANCIAL_TOKENIZATION_VERSION,
        "phrase_matching_version": PHRASE_MATCHING_VERSION,
        "inflection_rule_version": INFLECTION_RULE_VERSION,
        "negation_rule_version": NEGATION_RULE_VERSION,
        "structured_content_rule_version": STRUCTURED_CONTENT_RULE_VERSION,
        "quality_thresholds_version": QUALITY_THRESHOLDS_VERSION,
        "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
        "report_side_quality_policy_version": REPORT_SIDE_QUALITY_POLICY_VERSION,
        "alignment_change_quality_policy_version": ALIGNMENT_CHANGE_QUALITY_POLICY_VERSION,
        "dictionaries": sorted(
            [{"name": d.name, "version": d.version, "source_hash": d.source_hash} for d in dictionaries],
            key=lambda d: (d["name"], d["version"]),
        ),
        "config": asdict(config),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
