import dataclasses

from market_documents.models.enums import AlignmentRunStatus, FeatureQuality, LanguageSignalQuality
from market_documents.services.financial_language_quality import (
    AlignmentChangeQualityInputs,
    QualityAssessment,
    ReportSideQualityInputs,
    assess_alignment_change_quality,
    assess_report_side_quality,
    combine_quality_for_deprecated_composite,
)

# --------------------------------------------------------------------------
# Report-side quality -- never depends on alignment confidence/collision.
# --------------------------------------------------------------------------


def _report_side_inputs(**overrides):
    base = dict(
        is_transition=False,
        irregular_gap=False,
        primary_narrative_word_coverage_earlier=0.9,
        primary_narrative_word_coverage_later=0.9,
        dictionary_match_rate_earlier=0.1,
        dictionary_match_rate_later=0.1,
    )
    base.update(overrides)
    return ReportSideQualityInputs(**base)


def test_report_side_quality_has_no_alignment_confidence_input():
    """Type-level guarantee: there is no field on ReportSideQualityInputs
    that could carry alignment confidence, collision, margin, or
    uniqueness information -- report-side rates never depend on exact
    passage-to-passage correspondence."""
    field_names = {f.name for f in dataclasses.fields(ReportSideQualityInputs)}
    forbidden_substrings = ("confidence", "collision", "margin", "ambiguous", "unmatched", "feature_quality")
    assert not any(any(s in name for s in forbidden_substrings) for name in field_names)


def test_report_side_good_when_everything_clean():
    result = assess_report_side_quality(_report_side_inputs())
    assert result.quality == LanguageSignalQuality.GOOD
    assert result.primary_eligible is True
    assert result.warning_reasons is None


def test_report_side_needs_review_below_primary_narrative_coverage():
    result = assess_report_side_quality(_report_side_inputs(primary_narrative_word_coverage_earlier=0.5))
    assert result.quality == LanguageSignalQuality.NEEDS_REVIEW
    assert result.primary_eligible is False


def test_report_side_none_coverage_does_not_trigger_review():
    result = assess_report_side_quality(
        _report_side_inputs(primary_narrative_word_coverage_earlier=None, primary_narrative_word_coverage_later=None)
    )
    assert result.quality == LanguageSignalQuality.GOOD


def test_report_side_transition_excluded_but_not_penalized_for_gap():
    result = assess_report_side_quality(_report_side_inputs(irregular_gap=True, is_transition=True))
    assert result.quality == LanguageSignalQuality.GOOD
    assert result.primary_eligible is False
    assert "transition" in (result.exclusion_reasons or "")


def test_report_side_irregular_gap_without_transition_is_needs_review():
    result = assess_report_side_quality(_report_side_inputs(irregular_gap=True, is_transition=False))
    assert result.quality == LanguageSignalQuality.NEEDS_REVIEW
    assert result.primary_eligible is False


# --- Dictionary coverage banding (Milestone 6 recalibration) ---


def test_report_side_ordinary_dictionary_coverage_no_penalty():
    result = assess_report_side_quality(_report_side_inputs(dictionary_match_rate_earlier=0.06))
    assert result.quality == LanguageSignalQuality.GOOD


def test_report_side_borderline_dictionary_coverage_is_warning_not_needs_review():
    """KP2-like coverage (~0.045, below the 0.05 'ordinary' band but well
    above the 0.02 anomalous floor) must be a USABLE warning, never
    NEEDS_REVIEW -- it is plausible, evidence-supported coverage, not a
    dictionary malfunction."""
    result = assess_report_side_quality(_report_side_inputs(dictionary_match_rate_earlier=0.045))
    assert result.quality == LanguageSignalQuality.USABLE
    assert result.primary_eligible is True
    assert "borderline" in (result.warning_reasons or "")


def test_report_side_anomalously_low_dictionary_coverage_is_needs_review():
    result = assess_report_side_quality(_report_side_inputs(dictionary_match_rate_earlier=0.01))
    assert result.quality == LanguageSignalQuality.NEEDS_REVIEW
    assert "anomalously low" in (result.warning_reasons or "")


def test_report_side_zero_dictionary_matches_is_needs_review():
    result = assess_report_side_quality(_report_side_inputs(dictionary_match_rate_earlier=0.0))
    assert result.quality == LanguageSignalQuality.NEEDS_REVIEW


def test_report_side_direction_of_language_change_is_never_a_quality_input():
    field_names = {f.name for f in dataclasses.fields(ReportSideQualityInputs)}
    assert not any("negative" in name or "uncertainty_rate" in name or "risk" in name for name in field_names)


# --------------------------------------------------------------------------
# Alignment-change quality -- confidence/ambiguity/collision are legitimate.
# --------------------------------------------------------------------------


def _alignment_change_inputs(**overrides):
    base = dict(
        alignment_run_status=AlignmentRunStatus.COMPLETED,
        alignment_review_reason=None,
        feature_quality=FeatureQuality.GOOD,
        is_transition=False,
        irregular_gap=False,
        ambiguous_word_share=0.05,
        collision_flagged_word_share=0.3,
        unmatched_word_share=0.1,
    )
    base.update(overrides)
    return AlignmentChangeQualityInputs(**base)


def test_alignment_change_good_when_everything_clean():
    result = assess_alignment_change_quality(_alignment_change_inputs())
    assert result.quality == LanguageSignalQuality.GOOD
    assert result.primary_eligible is True


def test_alignment_change_upstream_feature_failed_propagates_to_failed():
    result = assess_alignment_change_quality(_alignment_change_inputs(feature_quality=FeatureQuality.FAILED))
    assert result.quality == LanguageSignalQuality.FAILED
    assert result.primary_eligible is False


def test_alignment_change_usable_when_upstream_feature_quality_needs_review():
    """Alignment-change quality DOES propagate upstream FeatureQuality --
    unlike report-side quality, NEW/REMOVED attribution genuinely reuses
    the alignment lineage that FeatureQuality describes."""
    result = assess_alignment_change_quality(_alignment_change_inputs(feature_quality=FeatureQuality.NEEDS_REVIEW))
    assert result.quality == LanguageSignalQuality.USABLE
    assert result.primary_eligible is True
    assert "upstream feature quality" in (result.warning_reasons or "")


def test_alignment_change_needs_review_above_ambiguous_share_threshold():
    result = assess_alignment_change_quality(_alignment_change_inputs(ambiguous_word_share=0.5))
    assert result.quality == LanguageSignalQuality.NEEDS_REVIEW
    assert result.primary_eligible is False


def test_alignment_change_moderate_collision_share_is_warning_not_needs_review():
    """A collision share above the warning threshold (0.60) but below the
    needs-review threshold (0.85) is this corpus's *normal* condition
    (median observed ~0.634) -- collision means non-unique, not wrong, so
    it must only ever produce a USABLE warning here, never an automatic
    mismatch verdict."""
    result = assess_alignment_change_quality(_alignment_change_inputs(collision_flagged_word_share=0.70))
    assert result.quality == LanguageSignalQuality.USABLE
    assert result.primary_eligible is True
    assert "non-unique" in (result.warning_reasons or "")
    assert "not a demonstrated mismatch" in (result.warning_reasons or "")


def test_alignment_change_excessive_collision_share_is_needs_review():
    result = assess_alignment_change_quality(_alignment_change_inputs(collision_flagged_word_share=0.90))
    assert result.quality == LanguageSignalQuality.NEEDS_REVIEW
    assert result.primary_eligible is False


def test_alignment_change_low_collision_share_no_penalty():
    result = assess_alignment_change_quality(_alignment_change_inputs(collision_flagged_word_share=0.1))
    assert result.quality == LanguageSignalQuality.GOOD


def test_alignment_change_high_unmatched_share_is_informational_only():
    """High content turnover (NEW+REMOVED) is a legitimate report
    characteristic, not evidence of a bad match -- informational warning
    only, never NEEDS_REVIEW on its own."""
    result = assess_alignment_change_quality(_alignment_change_inputs(unmatched_word_share=0.5))
    assert result.quality == LanguageSignalQuality.USABLE
    assert result.primary_eligible is True


def test_alignment_change_direction_of_language_change_is_never_a_quality_input():
    field_names = {f.name for f in dataclasses.fields(AlignmentChangeQualityInputs)}
    assert not any("negative" in name or "uncertainty_rate" in name or "risk" in name for name in field_names)


# --------------------------------------------------------------------------
# Independence between the two layers, and the deprecated composite.
# --------------------------------------------------------------------------


def test_report_side_and_alignment_change_are_independently_eligible():
    """The central recalibration guarantee: a pair with clean report-side
    inputs but a collision/ambiguity-heavy alignment-change population is
    report-side eligible while remaining alignment-change-qualified
    (not GOOD, but still USABLE/eligible here since collision alone -- even
    at a high, non-excessive share -- is a warning, not a hard block)."""
    report_side = assess_report_side_quality(_report_side_inputs())
    alignment_change = assess_alignment_change_quality(
        _alignment_change_inputs(collision_flagged_word_share=0.70, ambiguous_word_share=0.05)
    )
    assert report_side.primary_eligible is True
    assert report_side.quality == LanguageSignalQuality.GOOD
    assert alignment_change.primary_eligible is True
    assert alignment_change.quality == LanguageSignalQuality.USABLE


def test_report_side_eligible_while_alignment_change_is_not():
    """Excessive ambiguity must not block report-side eligibility at all --
    the two layers are fully independent primary-eligibility fields."""
    report_side = assess_report_side_quality(_report_side_inputs())
    alignment_change = assess_alignment_change_quality(_alignment_change_inputs(ambiguous_word_share=0.9))
    assert report_side.primary_eligible is True
    assert alignment_change.primary_eligible is False


def test_composite_quality_is_the_stricter_of_the_two():
    report_side = QualityAssessment(quality=LanguageSignalQuality.GOOD, warning_reasons=None, primary_eligible=True, exclusion_reasons=None)
    alignment_change = QualityAssessment(
        quality=LanguageSignalQuality.NEEDS_REVIEW, warning_reasons="ambiguous", primary_eligible=False, exclusion_reasons="bad"
    )
    composite = combine_quality_for_deprecated_composite(report_side, alignment_change)
    assert composite.quality == LanguageSignalQuality.NEEDS_REVIEW
    assert composite.primary_eligible is False
    assert "[alignment-change] ambiguous" in composite.warning_reasons


def test_composite_primary_eligible_requires_both_layers():
    report_side = QualityAssessment(quality=LanguageSignalQuality.GOOD, warning_reasons=None, primary_eligible=True, exclusion_reasons=None)
    alignment_change = QualityAssessment(
        quality=LanguageSignalQuality.USABLE, warning_reasons=None, primary_eligible=False, exclusion_reasons="excluded"
    )
    composite = combine_quality_for_deprecated_composite(report_side, alignment_change)
    assert composite.primary_eligible is False
    assert composite.quality == LanguageSignalQuality.USABLE
