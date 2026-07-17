import pytest

from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, PassageType
from market_documents.services.feature_config import FeatureConfig
from market_documents.services.feature_metrics import (
    AlignmentRowInput,
    aggregate_outcomes,
    compute_alignment_coverage,
    compute_document_change_transforms,
    compute_score_components,
    count_rates,
    is_heading_fragment,
    is_low_information,
    is_row_eligible,
    row_exclusion_kind,
    row_word_weight,
    safe_ratio,
    word_rates,
)

CONFIG = FeatureConfig()


def _row(status, earlier=None, later=None, earlier_type=None, later_type=None, confidence=AlignmentConfidence.HIGH):
    return AlignmentRowInput(
        alignment_status=status,
        confidence=confidence,
        earlier_word_count=earlier,
        later_word_count=later,
        earlier_passage_type=earlier_type,
        later_passage_type=later_type,
    )


def test_row_word_weight_matched_uses_mean_of_both_sides():
    row = _row(AlignmentStatus.SUBSTANTIALLY_MODIFIED, earlier=300, later=280, earlier_type=PassageType.PARAGRAPH, later_type=PassageType.PARAGRAPH)
    assert row_word_weight(row) == 290.0


def test_row_word_weight_new_uses_later_side_only():
    row = _row(AlignmentStatus.NEW, later=50, later_type=PassageType.PARAGRAPH)
    assert row_word_weight(row) == 50.0


def test_row_word_weight_removed_uses_earlier_side_only():
    row = _row(AlignmentStatus.REMOVED, earlier=40, earlier_type=PassageType.PARAGRAPH)
    assert row_word_weight(row) == 40.0


def test_row_word_weight_ambiguous_uses_the_one_present_side():
    earlier_only = _row(AlignmentStatus.AMBIGUOUS, earlier=35, earlier_type=PassageType.PARAGRAPH)
    later_only = _row(AlignmentStatus.AMBIGUOUS, later=60, later_type=PassageType.PARAGRAPH)
    assert row_word_weight(earlier_only) == 35.0
    assert row_word_weight(later_only) == 60.0


def test_ambiguous_split_merge_rows_never_double_count_a_passage():
    """Each AMBIGUOUS row carries exactly one side's word count (the DB's
    partial unique indexes guarantee a passage is primary in at most one
    row), so summing per-row weights across a split/merge group can never
    double-count either passage."""
    split_later = _row(AlignmentStatus.AMBIGUOUS, later=45, later_type=PassageType.PARAGRAPH)
    merge_earlier = _row(AlignmentStatus.AMBIGUOUS, earlier=30, earlier_type=PassageType.PARAGRAPH)
    total = row_word_weight(split_later) + row_word_weight(merge_earlier)
    assert total == 75.0


def test_raw_outcome_counts_and_word_totals():
    rows = [
        _row(AlignmentStatus.UNCHANGED, earlier=100, later=100, earlier_type=PassageType.PARAGRAPH, later_type=PassageType.PARAGRAPH),
        _row(AlignmentStatus.UNCHANGED, earlier=50, later=50, earlier_type=PassageType.PARAGRAPH, later_type=PassageType.PARAGRAPH),
        _row(AlignmentStatus.NEW, later=20, later_type=PassageType.PARAGRAPH),
    ]
    agg = aggregate_outcomes(rows, eligible_only=False, config=CONFIG)
    assert agg.counts[AlignmentStatus.UNCHANGED] == 2
    assert agg.counts[AlignmentStatus.NEW] == 1
    assert agg.counts[AlignmentStatus.REMOVED] == 0
    assert agg.words[AlignmentStatus.UNCHANGED] == 150.0
    assert agg.words[AlignmentStatus.NEW] == 20.0


def test_many_tiny_headings_vs_one_large_body_word_weighting_differs_from_counts():
    """Synthetic example from the milestone: three tiny unchanged headings
    (10 words each) plus one large substantially-modified body passage
    (300/280 words). By count, UNCHANGED dominates 3:1; by word weight, the
    single large SUBSTANTIALLY_MODIFIED passage dominates instead."""
    rows = [
        _row(AlignmentStatus.UNCHANGED, earlier=10, later=10, earlier_type=PassageType.HEADING_WITH_BODY, later_type=PassageType.HEADING_WITH_BODY),
        _row(AlignmentStatus.UNCHANGED, earlier=10, later=10, earlier_type=PassageType.HEADING_WITH_BODY, later_type=PassageType.HEADING_WITH_BODY),
        _row(AlignmentStatus.UNCHANGED, earlier=10, later=10, earlier_type=PassageType.HEADING_WITH_BODY, later_type=PassageType.HEADING_WITH_BODY),
        _row(AlignmentStatus.SUBSTANTIALLY_MODIFIED, earlier=300, later=280, earlier_type=PassageType.PARAGRAPH, later_type=PassageType.PARAGRAPH),
    ]
    raw = aggregate_outcomes(rows, eligible_only=False, config=CONFIG)
    raw_counts = count_rates(raw)
    raw_words = word_rates(raw)
    # By raw count, UNCHANGED (3 of 4 rows) dominates.
    assert raw_counts[AlignmentStatus.UNCHANGED] == 0.75
    # By word weight, the single large SUBSTANTIALLY_MODIFIED passage dominates.
    assert raw_words[AlignmentStatus.SUBSTANTIALLY_MODIFIED] > raw_words[AlignmentStatus.UNCHANGED]

    # The eligible (feature-local low-information floor default: 40 words)
    # population excludes the three tiny headings entirely.
    eligible = aggregate_outcomes(rows, eligible_only=True, config=CONFIG)
    assert eligible.counts[AlignmentStatus.UNCHANGED] == 0
    assert eligible.counts[AlignmentStatus.SUBSTANTIALLY_MODIFIED] == 1
    assert eligible.words[AlignmentStatus.SUBSTANTIALLY_MODIFIED] == 290.0


def test_all_passage_aggregate_is_unaffected_by_eligibility_filter():
    rows = [
        _row(AlignmentStatus.UNCHANGED, earlier=5, later=5, earlier_type=PassageType.HEADING_WITH_BODY, later_type=PassageType.HEADING_WITH_BODY),
    ]
    raw = aggregate_outcomes(rows, eligible_only=False, config=CONFIG)
    eligible = aggregate_outcomes(rows, eligible_only=True, config=CONFIG)
    assert raw.counts[AlignmentStatus.UNCHANGED] == 1
    assert eligible.counts[AlignmentStatus.UNCHANGED] == 0


def test_is_low_information_and_heading_fragment_rules():
    assert is_low_information(39, CONFIG) is True
    assert is_low_information(40, CONFIG) is False
    assert is_heading_fragment(20, PassageType.HEADING_WITH_BODY, CONFIG) is True
    assert is_heading_fragment(20, PassageType.PARAGRAPH, CONFIG) is False
    assert is_heading_fragment(200, PassageType.HEADING_WITH_BODY, CONFIG) is False


def test_row_exclusion_kind_classifies_heading_vs_plain_low_information():
    heading_row = _row(AlignmentStatus.UNCHANGED, earlier=10, later=10, earlier_type=PassageType.HEADING_WITH_BODY, later_type=PassageType.HEADING_WITH_BODY)
    plain_row = _row(AlignmentStatus.UNCHANGED, earlier=10, later=10, earlier_type=PassageType.PARAGRAPH, later_type=PassageType.PARAGRAPH)
    eligible_row = _row(AlignmentStatus.UNCHANGED, earlier=100, later=100, earlier_type=PassageType.PARAGRAPH, later_type=PassageType.PARAGRAPH)
    assert row_exclusion_kind(heading_row, CONFIG) == "heading_fragment"
    assert row_exclusion_kind(plain_row, CONFIG) == "low_information"
    assert row_exclusion_kind(eligible_row, CONFIG) is None
    assert is_row_eligible(eligible_row, CONFIG) is True
    assert is_row_eligible(heading_row, CONFIG) is False


def test_count_rates_zero_denominator_returns_none_not_zero():
    from market_documents.services.feature_metrics import OutcomeAggregate

    empty = OutcomeAggregate(counts={s: 0 for s in AlignmentStatus}, words={s: 0.0 for s in AlignmentStatus})
    rates = count_rates(empty)
    assert all(v is None for v in rates.values())
    word_rate_values = word_rates(empty)
    assert all(v is None for v in word_rate_values.values())


def test_safe_ratio_zero_denominator_is_none():
    assert safe_ratio(5, 0) is None
    assert safe_ratio(0, 0) is None
    assert safe_ratio(5, 10) == 0.5


def test_compute_alignment_coverage_counts_each_side_independently():
    rows = [
        _row(AlignmentStatus.UNCHANGED, earlier=100, later=100, earlier_type=PassageType.PARAGRAPH, later_type=PassageType.PARAGRAPH),
        _row(AlignmentStatus.NEW, later=20, later_type=PassageType.PARAGRAPH),
    ]
    coverage = compute_alignment_coverage(
        rows, earlier_total_count=2, later_total_count=2, earlier_total_words=150, later_total_words=170
    )
    # earlier covered: 1 of 2; later covered: 2 of 2 -> (1+2)/(2+2) = 0.75
    assert coverage.coverage_count == 0.75
    # earlier words covered: 100 of 150; later words covered: 120 of 170 -> (100+120)/(150+170)
    assert coverage.coverage_words == (100 + 120) / (150 + 170)


def test_compute_document_change_transforms_inverts_similarity_and_spread():
    transforms = compute_document_change_transforms(
        cosine=0.9, bigram_jaccard=0.8, edit_similarity=0.85, diff_similarity=0.7, word_change_ratio=-0.2
    )
    assert transforms.cosine_change == pytest.approx(0.1)
    assert transforms.bigram_jaccard_change == pytest.approx(0.2)
    assert transforms.word_change_ratio_abs == pytest.approx(0.2)
    assert transforms.metric_disagreement_spread == pytest.approx(0.2)  # max(0.9,0.8,0.85,0.7) - min(...)


def test_compute_document_change_transforms_handles_missing_diff():
    transforms = compute_document_change_transforms(
        cosine=0.9, bigram_jaccard=0.8, edit_similarity=0.85, diff_similarity=None, word_change_ratio=None
    )
    assert transforms.diff_similarity_change is None
    assert transforms.word_change_ratio_abs is None
    assert transforms.metric_disagreement_spread is not None


def test_compute_score_components_unchanged_contributes_zero_by_construction():
    rates = {status: 0.0 for status in AlignmentStatus}
    rates[AlignmentStatus.UNCHANGED] = 1.0
    components = compute_score_components(rates, CONFIG)
    assert components.unchanged == 0.0  # weight is 0.0 by default
    assert components.total == 0.0


def test_compute_score_components_total_is_none_when_any_rate_missing():
    rates = {status: None for status in AlignmentStatus}
    components = compute_score_components(rates, CONFIG)
    assert components.total is None


def test_compute_score_components_bounded_to_unit_interval_even_with_inflated_weight():
    inflated_config = FeatureConfig(new_weight=2.0)
    rates = {status: 0.0 for status in AlignmentStatus}
    rates[AlignmentStatus.NEW] = 1.0
    components = compute_score_components(rates, inflated_config)
    assert components.new == 2.0
    assert components.total == 1.0  # clamped, never fabricated above 1.0


def test_compute_score_components_realistic_weighted_sum():
    rates = {
        AlignmentStatus.UNCHANGED: 0.5,
        AlignmentStatus.LIGHTLY_MODIFIED: 0.2,
        AlignmentStatus.SUBSTANTIALLY_MODIFIED: 0.1,
        AlignmentStatus.NEW: 0.1,
        AlignmentStatus.REMOVED: 0.1,
        AlignmentStatus.AMBIGUOUS: 0.0,
    }
    components = compute_score_components(rates, CONFIG)
    expected = (
        0.5 * CONFIG.unchanged_weight
        + 0.2 * CONFIG.lightly_modified_weight
        + 0.1 * CONFIG.substantially_modified_weight
        + 0.1 * CONFIG.new_weight
        + 0.1 * CONFIG.removed_weight
        + 0.0 * CONFIG.ambiguous_weight
    )
    assert components.total == pytest.approx(expected)

