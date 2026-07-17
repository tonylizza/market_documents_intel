from market_documents.models.enums import AlignmentRunStatus, FeatureQuality, SimilarityResultQuality
from market_documents.services.feature_config import FeatureConfig
from market_documents.services.feature_quality import QualityInputs, assess_feature_quality

CONFIG = FeatureConfig()


def _inputs(**overrides) -> QualityInputs:
    defaults = dict(
        alignment_run_status=AlignmentRunStatus.COMPLETED,
        alignment_review_reason=None,
        document_quality=SimilarityResultQuality.GOOD,
        is_transition=False,
        irregular_gap=False,
        alignment_coverage_count=0.95,
        alignment_coverage_words=0.95,
        embedded_coverage_earlier=0.95,
        embedded_coverage_later=0.95,
        ambiguous_word_share=0.02,
        low_confidence_share=0.05,
        disclosure_change_score=0.2,
    )
    defaults.update(overrides)
    return QualityInputs(**defaults)


def test_clean_inputs_yield_good_quality_and_primary_eligible():
    assessment = assess_feature_quality(_inputs(), CONFIG)
    assert assessment.quality == FeatureQuality.GOOD
    assert assessment.primary_eligible is True
    assert assessment.exclusion_reasons is None


def test_document_quality_failed_forces_feature_quality_failed_and_no_row_omitted_reasons():
    assessment = assess_feature_quality(_inputs(document_quality=SimilarityResultQuality.FAILED), CONFIG)
    assert assessment.quality == FeatureQuality.FAILED
    assert assessment.primary_eligible is False
    assert "FAILED" in assessment.exclusion_reasons


def test_alignment_completed_with_warnings_alone_is_usable_not_needs_review():
    assessment = assess_feature_quality(
        _inputs(alignment_run_status=AlignmentRunStatus.COMPLETED_WITH_WARNINGS, alignment_review_reason="minor note"),
        CONFIG,
    )
    assert assessment.quality == FeatureQuality.USABLE
    assert assessment.primary_eligible is True
    assert "minor note" in assessment.warning_reasons


def test_irregular_gap_without_transition_flag_triggers_needs_review_and_exclusion():
    assessment = assess_feature_quality(_inputs(irregular_gap=True, is_transition=False), CONFIG)
    assert assessment.quality == FeatureQuality.NEEDS_REVIEW
    assert assessment.primary_eligible is False
    assert "irregular reporting gap" in assessment.warning_reasons


def test_irregular_gap_on_approved_transition_is_informational_only_but_still_excluded():
    """Milestone rule: approved transition handling must not degrade quality
    on its own, but the pair is still excluded from primary annual ranking."""
    assessment = assess_feature_quality(_inputs(irregular_gap=True, is_transition=True), CONFIG)
    assert assessment.quality == FeatureQuality.GOOD
    assert assessment.primary_eligible is False
    assert "transition-period pair" in assessment.exclusion_reasons
    assert "irregular reporting gap excluded" in assessment.exclusion_reasons


def test_document_quality_needs_review_triggers_feature_needs_review():
    assessment = assess_feature_quality(_inputs(document_quality=SimilarityResultQuality.NEEDS_REVIEW), CONFIG)
    assert assessment.quality == FeatureQuality.NEEDS_REVIEW


def test_insufficient_alignment_coverage_triggers_needs_review_and_exclusion():
    assessment = assess_feature_quality(
        _inputs(alignment_coverage_words=0.3, disclosure_change_score=None), CONFIG
    )
    assert assessment.quality == FeatureQuality.NEEDS_REVIEW
    assert assessment.primary_eligible is False
    assert "disclosure_change_score unavailable" in assessment.exclusion_reasons


def test_insufficient_embedding_coverage_triggers_needs_review():
    assessment = assess_feature_quality(_inputs(embedded_coverage_earlier=0.5), CONFIG)
    assert assessment.quality == FeatureQuality.NEEDS_REVIEW
    assert "earlier embedding coverage" in assessment.warning_reasons


def test_high_ambiguous_word_share_triggers_needs_review():
    assessment = assess_feature_quality(_inputs(ambiguous_word_share=0.5), CONFIG)
    assert assessment.quality == FeatureQuality.NEEDS_REVIEW
    assert "ambiguous word share" in assessment.warning_reasons


def test_high_low_confidence_share_triggers_needs_review():
    assessment = assess_feature_quality(_inputs(low_confidence_share=0.5), CONFIG)
    assert assessment.quality == FeatureQuality.NEEDS_REVIEW
    assert "confidence share" in assessment.warning_reasons


def test_missing_disclosure_change_score_alone_excludes_from_primary_even_if_quality_good():
    assessment = assess_feature_quality(_inputs(disclosure_change_score=None), CONFIG)
    assert assessment.quality == FeatureQuality.GOOD
    assert assessment.primary_eligible is False
    assert "disclosure_change_score unavailable" in assessment.exclusion_reasons


def test_metric_disagreement_is_not_a_quality_input_and_cannot_trigger_needs_review():
    """QualityInputs has no metric-disagreement field at all -- document-level
    metric disagreement (M3) must never, on its own, degrade feature quality."""
    assert not hasattr(QualityInputs, "document_metric_disagreement_spread")
    assessment = assess_feature_quality(_inputs(), CONFIG)
    assert assessment.quality == FeatureQuality.GOOD
