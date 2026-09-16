"""Pure tests for `services.structured_table_comparison` (Track 7C.4)."""

import uuid

from market_documents.models.enums import (
    AlignmentConfidence,
    StructuredCellStatus,
    StructuredColumnAlignmentStatus,
    StructuredComparabilityStatus,
    StructuredRowAlignmentStatus,
    StructuredValueChangeEventType,
)
from market_documents.services.structured_table_comparison import (
    CellView,
    ColumnCandidate,
    RowCandidate,
    align_columns,
    align_rows,
    classify_value_change,
)
from market_documents.services.structured_table_config import TOTAL_REMUNERATION_OUTCOMES


def _row(identity, statuses):
    return RowCandidate(id=uuid.uuid4(), position=0, normalized_identity=identity, cell_statuses=tuple(statuses))


def test_row_matched_when_present_both_sides():
    e = _row("h boonzaaier", [StructuredCellStatus.NUMERIC])
    l = _row("h boonzaaier", [StructuredCellStatus.NUMERIC])
    decisions = align_rows([e], [l])
    assert len(decisions) == 1
    assert decisions[0].status == StructuredRowAlignmentStatus.MATCHED


def test_row_removed_when_only_earlier():
    e = _row("w britz", [StructuredCellStatus.NUMERIC])
    decisions = align_rows([e], [])
    assert decisions[0].status == StructuredRowAlignmentStatus.REMOVED
    assert decisions[0].later_row_id is None


def test_row_added_when_only_later():
    l = _row("g van wyk", [StructuredCellStatus.NUMERIC])
    decisions = align_rows([], [l])
    assert decisions[0].status == StructuredRowAlignmentStatus.ADDED
    assert decisions[0].earlier_row_id is None


def test_row_comparative_only_when_later_all_nil_but_earlier_real():
    e = _row("w britz", [StructuredCellStatus.NUMERIC, StructuredCellStatus.NUMERIC])
    l = _row("w britz", [StructuredCellStatus.NIL_DASH, StructuredCellStatus.MISSING])
    decisions = align_rows([e], [l])
    assert decisions[0].status == StructuredRowAlignmentStatus.COMPARATIVE_ONLY


def test_row_succession_never_merged_always_removed_plus_added():
    # A departure and a new hire in the same table-year must never be
    # treated as one comparison subject (brief Section 13, explicit).
    e = _row("a banderker", [StructuredCellStatus.NUMERIC])
    l = _row("g van wyk", [StructuredCellStatus.NUMERIC])
    decisions = align_rows([e], [l])
    statuses = {d.status for d in decisions}
    assert statuses == {StructuredRowAlignmentStatus.REMOVED, StructuredRowAlignmentStatus.ADDED}
    assert len(decisions) == 2


def _col(key, position, restated=False):
    return ColumnCandidate(id=uuid.uuid4(), position=position, normalized_key=key, is_restated=restated)


def test_column_matched_directly_comparable_by_default():
    e = _col("base_pay", 0)
    l = _col("base_pay", 0)
    decisions = align_columns([e], [l], TOTAL_REMUNERATION_OUTCOMES, earlier_year=2020, later_year=2021)
    assert decisions[0].status == StructuredColumnAlignmentStatus.MATCHED
    assert decisions[0].comparability_status == StructuredComparabilityStatus.DIRECTLY_COMPARABLE


def test_column_schema_change_applies_partially_comparable_not_removed():
    e = _col("sti", 4)
    l = _col("sti", 4)
    decisions = align_columns([e], [l], TOTAL_REMUNERATION_OUTCOMES, earlier_year=2022, later_year=2023)
    assert decisions[0].status == StructuredColumnAlignmentStatus.MATCHED
    assert decisions[0].comparability_status == StructuredComparabilityStatus.PARTIALLY_COMPARABLE_SCHEMA_CHANGED


def test_column_current_and_restated_slots_do_not_collide():
    # Two columns can share a normalized_key (current vs. restated) --
    # alignment identity must be the (key, is_restated) pair, or one
    # silently overwrites the other in a plain key->column dict.
    earlier = [_col("base_pay", 0, restated=False), _col("base_pay", 1, restated=True)]
    later = [_col("base_pay", 0, restated=False), _col("base_pay", 1, restated=True)]
    decisions = align_columns(earlier, later, TOTAL_REMUNERATION_OUTCOMES, earlier_year=2020, later_year=2021)
    assert len(decisions) == 2
    assert all(d.status == StructuredColumnAlignmentStatus.MATCHED for d in decisions)


def test_column_added_and_removed():
    decisions = align_columns([_col("lti", 6)], [_col("base_pay", 0)], TOTAL_REMUNERATION_OUTCOMES, 2020, 2021)
    statuses = {d.status for d in decisions}
    assert statuses == {StructuredColumnAlignmentStatus.REMOVED, StructuredColumnAlignmentStatus.ADDED}
    for d in decisions:
        assert d.comparability_status == StructuredComparabilityStatus.NOT_COMPARABLE


def _cell(raw, status, numeric=None):
    return CellView(id=uuid.uuid4(), raw_value=raw, cell_status=status, parsed_numeric_value=numeric)


def test_value_increased_with_pct_change():
    e = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    l = _cell("150", StructuredCellStatus.NUMERIC, 150.0)
    event, absolute, pct = classify_value_change(
        e, l, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event == StructuredValueChangeEventType.VALUE_INCREASED
    assert absolute == 50.0
    assert pct == 0.5


def test_value_decreased():
    e = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    l = _cell("80", StructuredCellStatus.NUMERIC, 80.0)
    event, absolute, pct = classify_value_change(
        e, l, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event == StructuredValueChangeEventType.VALUE_DECREASED
    assert absolute == -20.0
    assert pct == -0.2


def test_value_unchanged_zero_absolute():
    e = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    l = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    event, absolute, pct = classify_value_change(
        e, l, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event == StructuredValueChangeEventType.VALUE_UNCHANGED
    assert absolute == 0.0
    assert pct == 0.0


def test_pct_change_null_on_zero_denominator():
    e = _cell("0", StructuredCellStatus.ZERO, 0.0)
    l = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    event, absolute, pct = classify_value_change(
        e, l, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event == StructuredValueChangeEventType.ZERO_TO_VALUE
    assert absolute is None
    assert pct is None


def test_nil_to_value_and_value_to_nil():
    nil = _cell("–", StructuredCellStatus.NIL_DASH)
    val = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    event, absolute, pct = classify_value_change(
        nil, val, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event == StructuredValueChangeEventType.NIL_TO_VALUE
    assert absolute is None and pct is None

    event2, _, _ = classify_value_change(
        val, nil, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event2 == StructuredValueChangeEventType.VALUE_TO_NIL


def test_missing_to_value_and_value_to_missing():
    missing = _cell(None, StructuredCellStatus.MISSING)
    val = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    event, _, _ = classify_value_change(
        missing, val, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event == StructuredValueChangeEventType.MISSING_TO_VALUE

    event2, _, _ = classify_value_change(
        val, missing, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event2 == StructuredValueChangeEventType.VALUE_TO_MISSING


def test_schema_changed_suppresses_ordinary_comparison():
    e = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    l = _cell("2000", StructuredCellStatus.NUMERIC, 2000.0)
    event, absolute, pct = classify_value_change(
        e, l, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.PARTIALLY_COMPARABLE_SCHEMA_CHANGED
    )
    assert event == StructuredValueChangeEventType.SCHEMA_CHANGED
    assert absolute is None and pct is None


def test_comparative_only_row_suppresses_value_diff_regardless_of_cells():
    e = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    l = _cell("–", StructuredCellStatus.NIL_DASH)
    event, absolute, pct = classify_value_change(
        e, l, StructuredRowAlignmentStatus.COMPARATIVE_ONLY, StructuredComparabilityStatus.DIRECTLY_COMPARABLE
    )
    assert event == StructuredValueChangeEventType.COMPARATIVE_ONLY
    assert absolute is None and pct is None


def test_not_comparable_never_fabricates_a_change():
    e = _cell("100", StructuredCellStatus.NUMERIC, 100.0)
    l = _cell("200", StructuredCellStatus.NUMERIC, 200.0)
    event, absolute, pct = classify_value_change(
        e, l, StructuredRowAlignmentStatus.MATCHED, StructuredComparabilityStatus.NOT_COMPARABLE
    )
    assert event == StructuredValueChangeEventType.VALUE_NOT_COMPARABLE
    assert absolute is None and pct is None
