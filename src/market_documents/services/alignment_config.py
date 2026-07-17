"""Centralized, versioned passage-alignment thresholds, weights, and configuration.

Mirrors `similarity_config.py`/`passage_config.py`/`embedding_config.py`.
Bump the relevant `*_VERSION` constant whenever a weight, threshold, or
algorithm changes -- that is what forces a fresh `AlignmentRun` instead of
silently reusing a stale one.

Weights and thresholds below are provisional, set from first principles
(not tuned against market outcomes, per the milestone's explicit
prohibition) and are expected to be revised after inspecting real alignment
results on the 7 existing ReportPairs.
"""

import hashlib
import json
from dataclasses import asdict, dataclass

ALGORITHM_VERSION = "1.0.0"

CANDIDATE_CONFIG_VERSION = 1
SCORING_CONFIG_VERSION = 1
CLASSIFICATION_THRESHOLDS_VERSION = 1
CONFIDENCE_THRESHOLDS_VERSION = 1
# v1 = detect likely split/merge cases and mark them AMBIGUOUS; does not
# attempt constrained one-to-two/two-to-one acceptance (deferred, see
# passage_alignment.py's split/merge detection docstring).
SPLIT_MERGE_POLICY_VERSION = 1


@dataclass(frozen=True)
class AlignmentConfig:
    # --- Candidate generation ---
    top_k: int = 5
    min_semantic_similarity: float = 0.50

    # --- Combined scoring weights (must sum to 1.0) ---
    weight_semantic: float = 0.50
    weight_lexical: float = 0.30
    weight_heading: float = 0.10
    weight_position: float = 0.10

    # A candidate below this combined score is never accepted, regardless
    # of rank -- prevents "always accept the top result" behavior when even
    # the best candidate is weak.
    min_combined_score_for_acceptance: float = 0.45

    # --- Change classification (applied only to accepted correspondences) ---
    unchanged_semantic_threshold: float = 0.95
    unchanged_lexical_threshold: float = 0.90
    # length_ratio is shorter/longer word count, bounded (0, 1]; 1.0 = equal length.
    unchanged_length_ratio_min: float = 0.85
    # LIGHTLY_MODIFIED is gated on semantic similarity alone (see
    # alignment_quality.classify_alignment's docstring for why lexical
    # evidence must not additionally gate this tier).
    lightly_modified_semantic_threshold: float = 0.85

    # --- Semantic/lexical disagreement (informational, not a status) ---
    disagreement_high_semantic_threshold: float = 0.85
    disagreement_low_lexical_threshold: float = 0.40
    disagreement_low_semantic_threshold: float = 0.55
    disagreement_high_lexical_threshold: float = 0.75

    # --- Split/merge detection (v1: detect + flag AMBIGUOUS only) ---
    split_merge_candidate_min_score: float = 0.35

    # --- Confidence ---
    low_margin_threshold: float = 0.03
    medium_margin_threshold: float = 0.08
    irregular_gap_months_threshold: int = 18


ALIGNMENT_CONFIG = AlignmentConfig()


def compute_configuration_hash(config: AlignmentConfig = ALIGNMENT_CONFIG) -> str:
    """Deterministic fingerprint of everything that can change alignment output.

    Does not include the earlier/later segmentation and embedding run IDs --
    those are pinned separately on `AlignmentRun` and combined with this hash
    by the orchestration layer's skip check, since the same alignment
    configuration run against different source runs must not be treated as
    identical.
    """
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "candidate_config_version": CANDIDATE_CONFIG_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "classification_thresholds_version": CLASSIFICATION_THRESHOLDS_VERSION,
        "confidence_thresholds_version": CONFIDENCE_THRESHOLDS_VERSION,
        "split_merge_policy_version": SPLIT_MERGE_POLICY_VERSION,
        "config": asdict(config),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
