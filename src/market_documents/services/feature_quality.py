"""Feature-result quality diagnostics and primary-analysis eligibility.

Mirrors `similarity_quality.py`'s shape: every threshold comes from
`FeatureConfig`, and a result is never classified GOOD merely because the
computation completed -- GOOD additionally requires clean upstream run
status, adequate coverage, and the absence of every review trigger.

Two milestone rules are deliberately encoded here rather than left
implicit: (1) document-level metric disagreement (M3) is never, on its own,
a feature-quality review trigger -- it is a separate diagnostic axis; (2) an
irregular reporting gap on a pair already flagged `is_transition` is
"approved transition handling" and does not by itself degrade quality, even
though it still excludes the pair from primary annual ranking below.
"""

from dataclasses import dataclass

from market_documents.models.enums import AlignmentRunStatus, FeatureQuality, SimilarityResultQuality
from market_documents.services.feature_config import FEATURE_CONFIG, FeatureConfig


@dataclass(frozen=True)
class QualityInputs:
    alignment_run_status: AlignmentRunStatus
    alignment_review_reason: str | None
    document_quality: SimilarityResultQuality | None
    is_transition: bool
    irregular_gap: bool
    alignment_coverage_count: float | None
    alignment_coverage_words: float | None
    embedded_coverage_earlier: float | None
    embedded_coverage_later: float | None
    ambiguous_word_share: float | None
    low_confidence_share: float | None
    disclosure_change_score: float | None


@dataclass(frozen=True)
class QualityAssessment:
    quality: FeatureQuality
    warning_reasons: str | None
    primary_eligible: bool
    exclusion_reasons: str | None


def assess_feature_quality(
    inputs: QualityInputs, config: FeatureConfig = FEATURE_CONFIG
) -> QualityAssessment:
    if inputs.document_quality == SimilarityResultQuality.FAILED:
        reason = "document-level similarity quality is FAILED"
        return QualityAssessment(
            quality=FeatureQuality.FAILED,
            warning_reasons=reason,
            primary_eligible=False,
            exclusion_reasons=reason,
        )

    reasons: list[str] = []
    # Informational notes are surfaced in warning_reasons but never
    # contribute to `needs_review` -- distinct from `reasons`, which do.
    informational: list[str] = []

    weak_source = inputs.alignment_run_status == AlignmentRunStatus.COMPLETED_WITH_WARNINGS
    if weak_source:
        informational.append(
            f"alignment run completed with warnings: {inputs.alignment_review_reason or 'unspecified'}"
        )

    if inputs.document_quality == SimilarityResultQuality.NEEDS_REVIEW:
        reasons.append("document-level similarity quality is NEEDS_REVIEW")

    if inputs.irregular_gap:
        if inputs.is_transition:
            informational.append("irregular gap on an approved transition-period pair")
        else:
            reasons.append("irregular reporting gap: unexplained, not a flagged transition period")

    if (
        inputs.alignment_coverage_count is not None
        and inputs.alignment_coverage_count < config.minimum_alignment_coverage
    ):
        reasons.append(
            f"alignment coverage (count) {inputs.alignment_coverage_count:.2f} "
            f"below threshold ({config.minimum_alignment_coverage})"
        )
    if (
        inputs.alignment_coverage_words is not None
        and inputs.alignment_coverage_words < config.minimum_alignment_coverage
    ):
        reasons.append(
            f"alignment coverage (words) {inputs.alignment_coverage_words:.2f} "
            f"below threshold ({config.minimum_alignment_coverage})"
        )

    for label, coverage in (
        ("earlier", inputs.embedded_coverage_earlier),
        ("later", inputs.embedded_coverage_later),
    ):
        if coverage is not None and coverage < config.minimum_embedding_coverage:
            reasons.append(
                f"{label} embedding coverage {coverage:.2f} below threshold ({config.minimum_embedding_coverage})"
            )

    if (
        inputs.ambiguous_word_share is not None
        and inputs.ambiguous_word_share > config.ambiguous_word_share_threshold
    ):
        reasons.append(
            f"ambiguous word share {inputs.ambiguous_word_share:.2f} "
            f"exceeds tolerance ({config.ambiguous_word_share_threshold})"
        )

    if (
        inputs.low_confidence_share is not None
        and inputs.low_confidence_share > config.low_confidence_share_threshold
    ):
        reasons.append(
            f"low/needs-review confidence share {inputs.low_confidence_share:.2f} "
            f"exceeds tolerance ({config.low_confidence_share_threshold})"
        )

    needs_review = bool(reasons)
    if needs_review:
        quality = FeatureQuality.NEEDS_REVIEW
    elif weak_source:
        quality = FeatureQuality.USABLE
    else:
        quality = FeatureQuality.GOOD

    primary_eligible = (
        quality in (FeatureQuality.GOOD, FeatureQuality.USABLE)
        and not inputs.is_transition
        and not inputs.irregular_gap
        and inputs.disclosure_change_score is not None
    )
    exclusion_reason_parts: list[str] = []
    if not primary_eligible:
        if quality not in (FeatureQuality.GOOD, FeatureQuality.USABLE):
            exclusion_reason_parts.append(f"feature quality is {quality.value}")
        if inputs.is_transition:
            exclusion_reason_parts.append("transition-period pair excluded from primary analysis by default")
        if inputs.irregular_gap:
            exclusion_reason_parts.append("irregular reporting gap excluded from primary analysis by default")
        if inputs.disclosure_change_score is None:
            exclusion_reason_parts.append("disclosure_change_score unavailable (insufficient coverage or quality)")

    all_notes = reasons + informational
    return QualityAssessment(
        quality=quality,
        warning_reasons="; ".join(all_notes) if all_notes else None,
        primary_eligible=primary_eligible,
        exclusion_reasons="; ".join(exclusion_reason_parts) if exclusion_reason_parts else None,
    )
