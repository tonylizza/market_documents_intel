"""Similarity-result quality diagnostics and primary-analysis eligibility.

Mirrors `extraction_quality.py`'s shape: every threshold comes from
`SimilarityConfig`, and a result is never classified GOOD merely because
metrics computed -- GOOD additionally requires clean source-extraction
quality and the absence of every review trigger. USABLE and
COMPLETED_WITH_WARNINGS extraction inputs are legitimate and are not, on
their own, review triggers -- only NEEDS_REVIEW extraction quality is.
"""

from dataclasses import dataclass

from market_documents.models.enums import DiffMode, ExtractionQuality, SimilarityResultQuality
from market_documents.services.similarity_config import SIMILARITY_CONFIG, SimilarityConfig
from market_documents.services.similarity_metrics import LengthChangeFeatures, MetricSet

_METRIC_NAMES = ("lexical_cosine_similarity", "jaccard_similarity", "diff_similarity", "edit_similarity")


@dataclass(frozen=True)
class QualityAssessment:
    quality: SimilarityResultQuality
    review_reason: str | None
    primary_analysis_eligible: bool
    primary_analysis_exclusion_reason: str | None


def assess_similarity(
    *,
    metrics: MetricSet,
    length_features: LengthChangeFeatures,
    earlier_extraction_quality: ExtractionQuality,
    later_extraction_quality: ExtractionQuality,
    is_transition: bool,
    gap_months: int,
    config: SimilarityConfig = SIMILARITY_CONFIG,
) -> QualityAssessment:
    """Assess trustworthiness of one pair's similarity result.

    Called only once both narratives are confirmed non-empty (that
    eligibility gate lives in `similarity.py`, not here) -- this function
    assumes it has real metric attempts to evaluate, not a missing input.
    """
    reasons: list[str] = []
    # Informational notes are surfaced in review_reason but, unlike
    # `reasons`, never contribute to `needs_review` -- metric *availability*
    # (e.g. diff skipped for a very long document) is a separate concept
    # from result *quality*, per the diff-runtime-policy design.
    informational: list[str] = []

    metric_values = {
        "lexical_cosine_similarity": metrics.lexical_cosine_similarity,
        "jaccard_similarity": metrics.jaccard_similarity,
        "diff_similarity": metrics.diff_similarity,
        "edit_similarity": metrics.edit_similarity,
    }
    diff_skipped_for_size = metrics.diff_mode == DiffMode.SKIPPED_TOKEN_LIMIT
    if diff_skipped_for_size:
        informational.append("diff_similarity omitted: token count exceeds configured limit")

    failed_metrics = [
        name
        for name in _METRIC_NAMES
        if metric_values[name] is None and not (name == "diff_similarity" and diff_skipped_for_size)
    ]
    if failed_metrics:
        reasons.append(f"metric(s) undefined or non-finite: {', '.join(failed_metrics)}")

    if length_features.earlier_word_count < config.min_words_for_review:
        reasons.append(
            f"earlier narrative ({length_features.earlier_word_count} words) "
            f"below review threshold ({config.min_words_for_review})"
        )
    if length_features.later_word_count < config.min_words_for_review:
        reasons.append(
            f"later narrative ({length_features.later_word_count} words) "
            f"below review threshold ({config.min_words_for_review})"
        )

    shorter = min(length_features.earlier_word_count, length_features.later_word_count)
    longer = max(length_features.earlier_word_count, length_features.later_word_count)
    length_ratio = (longer / shorter) if shorter else None
    if length_ratio is not None and length_ratio > config.max_length_ratio_for_review:
        reasons.append(f"length ratio {length_ratio:.1f}x exceeds tolerance ({config.max_length_ratio_for_review}x)")

    if earlier_extraction_quality == ExtractionQuality.NEEDS_REVIEW:
        reasons.append("earlier report extraction quality is NEEDS_REVIEW")
    if later_extraction_quality == ExtractionQuality.NEEDS_REVIEW:
        reasons.append("later report extraction quality is NEEDS_REVIEW")

    if gap_months > config.max_gap_months_for_review:
        reasons.append(f"reporting gap ({gap_months} months) exceeds tolerance ({config.max_gap_months_for_review})")

    # Transition-pair status is deliberately NOT folded into `reasons`/
    # `review_reason`: it is tracked as its own independent axis (see
    # `primary_analysis_exclusion_reason` below) rather than degrading the
    # quality tier -- a transition pair's metrics can still be GOOD, it is
    # simply excluded from primary rankings by default.

    non_null_values = metrics.values()
    disagreement_spread: float | None = None
    if len(non_null_values) >= 2:
        disagreement_spread = max(non_null_values) - min(non_null_values)
        if disagreement_spread > config.metric_disagreement_threshold:
            reasons.append(
                f"metric disagreement spread {disagreement_spread:.2f} "
                f"exceeds tolerance ({config.metric_disagreement_threshold})"
            )

    needs_review = bool(reasons)
    weak_extraction_input = (
        earlier_extraction_quality != ExtractionQuality.GOOD
        or later_extraction_quality != ExtractionQuality.GOOD
    )

    if len(failed_metrics) == len(_METRIC_NAMES):
        quality = SimilarityResultQuality.FAILED
    elif needs_review:
        quality = SimilarityResultQuality.NEEDS_REVIEW
    elif weak_extraction_input:
        quality = SimilarityResultQuality.USABLE
        reasons.append("source extraction quality below GOOD on at least one side")
    else:
        quality = SimilarityResultQuality.GOOD

    primary_eligible = quality in (SimilarityResultQuality.GOOD, SimilarityResultQuality.USABLE) and not is_transition
    exclusion_reason: str | None = None
    if not primary_eligible:
        if is_transition:
            exclusion_reason = "transition-period pair excluded from primary analysis by default"
        elif quality == SimilarityResultQuality.FAILED:
            exclusion_reason = "all similarity metrics failed"
        else:
            exclusion_reason = f"result quality is {quality.value}"

    all_notes = reasons + informational
    return QualityAssessment(
        quality=quality,
        review_reason="; ".join(all_notes) if all_notes else None,
        primary_analysis_eligible=primary_eligible,
        primary_analysis_exclusion_reason=exclusion_reason,
    )
