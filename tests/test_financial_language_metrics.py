from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, ReportSide
from market_documents.services.financial_language_metrics import (
    SignalRowInput,
    aggregate_side,
    classify_collision,
    compute_core_category_change,
    custom_category_rate,
    dictionary_hits_by_confidence,
    dictionary_match_rate,
    forward_looking_caution_rate,
    hits_for_status,
    introduction_or_removal_rate,
    is_primary_narrative_eligible,
    net_tone,
    rate_change,
    rate_per_1000_words,
    safe_ratio,
)


def _row(
    side=ReportSide.EARLIER,
    status=AlignmentStatus.SUBSTANTIALLY_MODIFIED,
    confidence=AlignmentConfidence.HIGH,
    words=100,
    category=None,
    feature_eligible=True,
    positive=0,
    negative=0,
    uncertainty=0,
    litigious=0,
    constraining=0,
    strong_modal=0,
    weak_modal=0,
    total_hits=None,
    custom=None,
):
    total = total_hits if total_hits is not None else (positive + negative + uncertainty + litigious + constraining + strong_modal + weak_modal)
    return SignalRowInput(
        report_side=side,
        alignment_status=status,
        confidence=confidence,
        passage_word_count=words,
        structured_content_category=category,
        feature_eligible=feature_eligible,
        positive_count=positive,
        negative_count=negative,
        uncertainty_count=uncertainty,
        litigious_count=litigious,
        constraining_count=constraining,
        strong_modal_count=strong_modal,
        weak_modal_count=weak_modal,
        total_dictionary_hits=total,
        custom_category_hits=custom or {},
    )


# --------------------------------------------------------------------------
# Population / eligibility
# --------------------------------------------------------------------------


def test_primary_narrative_excludes_financial_table_rendered_as_prose():
    row = _row(category="financial_table_rendered_as_prose")
    assert is_primary_narrative_eligible(row) is False


def test_primary_narrative_retains_currency_exposure_mixed():
    row = _row(category="currency_exposure_table_mixed")
    assert is_primary_narrative_eligible(row) is True


def test_primary_narrative_retains_uncertain():
    row = _row(category="uncertain")
    assert is_primary_narrative_eligible(row) is True


def test_primary_narrative_retains_none_category():
    assert is_primary_narrative_eligible(_row(category=None)) is True


# --------------------------------------------------------------------------
# Rate formulas / zero denominators
# --------------------------------------------------------------------------


def test_safe_ratio_zero_denominator_is_none():
    assert safe_ratio(5, 0) is None


def test_safe_ratio_positive_denominator():
    assert safe_ratio(5, 10) == 0.5


def test_rate_per_1000_words():
    assert rate_per_1000_words(2, 100) == 20.0


def test_rate_per_1000_words_zero_words_is_none():
    assert rate_per_1000_words(2, 0) is None


def test_rate_change_none_if_either_side_missing():
    assert rate_change(None, 5.0) is None
    assert rate_change(5.0, None) is None


def test_rate_change_computes_difference():
    assert rate_change(8.0, 5.0) == 3.0


def test_net_tone_none_if_missing():
    assert net_tone(None, 1.0) is None


def test_net_tone_positive_minus_negative():
    assert net_tone(5.0, 2.0) == 3.0


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def test_aggregate_side_sums_words_and_counts():
    rows = [
        _row(side=ReportSide.EARLIER, words=100, positive=2, negative=1),
        _row(side=ReportSide.EARLIER, words=50, positive=1),
        _row(side=ReportSide.LATER, words=80, negative=3),
    ]
    earlier = aggregate_side(rows, ReportSide.EARLIER)
    assert earlier.words == 150
    assert earlier.category_totals["positive"] == 3
    assert earlier.category_totals["negative"] == 1


def test_aggregate_side_custom_category_totals():
    rows = [_row(side=ReportSide.EARLIER, custom={"risk": 2}), _row(side=ReportSide.EARLIER, custom={"risk": 1, "governance": 1})]
    earlier = aggregate_side(rows, ReportSide.EARLIER)
    assert earlier.custom_category_totals["risk"] == 3
    assert earlier.custom_category_totals["governance"] == 1


def test_compute_core_category_change():
    earlier = aggregate_side([_row(side=ReportSide.EARLIER, words=100, negative=1)], ReportSide.EARLIER)
    later = aggregate_side([_row(side=ReportSide.LATER, words=100, negative=3)], ReportSide.LATER)
    change = compute_core_category_change("negative", earlier, later)
    assert change.rate_earlier == 10.0
    assert change.rate_later == 30.0
    assert change.rate_change == 20.0
    assert change.rate_change_abs == 20.0


def test_dictionary_match_rate_uses_total_hits():
    side = aggregate_side([_row(words=100, positive=2, negative=1)], ReportSide.EARLIER)
    assert dictionary_match_rate(side) == 3 / 100


def test_custom_category_rate():
    side = aggregate_side([_row(words=200, custom={"risk": 4})], ReportSide.EARLIER)
    assert custom_category_rate(side, "risk") == 20.0


def test_forward_looking_caution_rate_combines_uncertainty_and_weak_modal():
    side = aggregate_side([_row(words=1000, uncertainty=5, weak_modal=3)], ReportSide.EARLIER)
    assert forward_looking_caution_rate(side) == 8.0


def test_dictionary_hits_by_confidence():
    rows = [
        _row(confidence=AlignmentConfidence.HIGH, total_hits=3),
        _row(confidence=AlignmentConfidence.MEDIUM, total_hits=2),
        _row(confidence=AlignmentConfidence.LOW, total_hits=10),
    ]
    assert dictionary_hits_by_confidence(rows, (AlignmentConfidence.HIGH,)) == 3
    assert dictionary_hits_by_confidence(rows, (AlignmentConfidence.HIGH, AlignmentConfidence.MEDIUM)) == 5


# --------------------------------------------------------------------------
# NEW / REMOVED / introduction-removal (direction always explicit)
# --------------------------------------------------------------------------


def test_hits_for_status_filters_by_alignment_status():
    rows = [
        _row(status=AlignmentStatus.NEW, side=ReportSide.LATER, words=50, negative=2),
        _row(status=AlignmentStatus.REMOVED, side=ReportSide.EARLIER, words=40, negative=1),
        _row(status=AlignmentStatus.SUBSTANTIALLY_MODIFIED, negative=99),
    ]
    new_hits = hits_for_status(rows, AlignmentStatus.NEW)
    assert new_hits.core["negative"] == 2
    assert new_hits.words == 50


def test_introduction_rate_from_new_rows_only():
    rows = [_row(status=AlignmentStatus.NEW, side=ReportSide.LATER, words=100, negative=4)]
    new_hits = hits_for_status(rows, AlignmentStatus.NEW)
    assert introduction_or_removal_rate(new_hits, "negative") == 40.0


def test_removal_rate_from_removed_rows_only():
    rows = [_row(status=AlignmentStatus.REMOVED, side=ReportSide.EARLIER, words=100, positive=2)]
    removed_hits = hits_for_status(rows, AlignmentStatus.REMOVED)
    assert introduction_or_removal_rate(removed_hits, "positive") == 20.0


def test_removed_negative_language_is_never_reinterpreted_as_positive():
    """Removing negative language must never register as a positive
    introduction -- direction stays explicit per category, so the positive
    rate here is a real, well-defined zero (no positive hits occurred),
    never a value derived from the negative hits that were removed."""
    rows = [_row(status=AlignmentStatus.REMOVED, side=ReportSide.EARLIER, words=100, negative=5)]
    removed_hits = hits_for_status(rows, AlignmentStatus.REMOVED)
    assert introduction_or_removal_rate(removed_hits, "negative") == 50.0
    assert introduction_or_removal_rate(removed_hits, "positive") == 0.0


def test_introduction_rate_zero_words_is_none():
    rows: list[SignalRowInput] = []
    status_hits = hits_for_status(rows, AlignmentStatus.NEW)
    assert introduction_or_removal_rate(status_hits, "negative") is None


# --------------------------------------------------------------------------
# Collision classification (Milestone 6 recalibration) -- real text written
# by `detect_candidate_collisions` in passage_alignment.py. Neither actual
# message contains the literal word "collision".
# --------------------------------------------------------------------------


def test_classify_collision_none_reason_is_false():
    assert classify_collision(None) is False


def test_classify_collision_empty_reason_is_false():
    assert classify_collision("") is False


def test_classify_collision_unrelated_reason_is_false():
    assert classify_collision("irregular reporting gap (96 months)") is False


def test_classify_collision_multi_claimant_reason_is_true():
    assert (
        classify_collision(
            "earlier passage also proposed above threshold by 2 other later passage(s) -- "
            "likely duplicated/boilerplate content, match may be arbitrary"
        )
        is True
    )


def test_classify_collision_exact_duplicate_reason_is_true():
    assert (
        classify_collision(
            "earlier passage's text exactly duplicates another earlier passage -- "
            "match cannot be disambiguated from content alone"
        )
        is True
    )


def test_classify_collision_case_insensitive():
    assert classify_collision("MATCH CANNOT BE DISAMBIGUATED FROM CONTENT ALONE") is True


def test_signal_row_input_collision_and_split_merge_default_false():
    row = _row()
    assert row.collision_flag is False
    assert row.split_merge_flag is False
