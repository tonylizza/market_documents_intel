"""Tests for Track 7A.3/7A.4's `publishing.cutover_publishing` -- the
publish-time caller of the already-validated Track 7C.6 `cutover_comparison`
functions.

Reuses `tests.test_cutover_comparison`'s fixture helpers directly (the same
cross-import convention `test_cutover_preflight.py` already uses) so this
module never re-derives its own ORM fixture setup.
"""

import uuid

from market_documents.models.enums import (
    AnalyticalMode,
    ComparisonResponseStatus,
    SemanticUnitAlignmentStatus,
    StructuredValueChangeEventType,
)
from market_documents.publishing.cutover_publishing import (
    build_narrative_comparison_rows,
    build_structured_comparison_rows,
)
from tests.test_cutover_comparison import (
    _alignment,
    _alignment_run,
    _canonical_block,
    _canonical_page,
    _canonical_run,
    _column_alignment,
    _company,
    _decision,
    _decision_run,
    _footnote,
    _lexical,
    _localization_run,
    _pair,
    _report,
    _row_alignment,
    _schedule_instance,
    _structured_table,
    _table_alignment_run,
    _table_extraction_run,
    _unit,
    _unit_run,
    _value_change_event,
)

_PUB_ARGS = {"publication_id": uuid.uuid4(), "publication_version": "test-cutover-publishing-v1"}


def test_narrative_resolved_row_built_from_matched_alignment(db_session):
    company = _company(db_session, "BEL")
    earlier_report = _report(db_session, company, 2018, "e")
    later_report = _report(db_session, company, 2019, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    earlier_loc = _localization_run(db_session, earlier_report)
    later_loc = _localization_run(db_session, later_report)
    earlier_instance = _schedule_instance(db_session, earlier_loc, earlier_report)
    later_instance = _schedule_instance(db_session, later_loc, later_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_loc)
    later_unit_run = _unit_run(db_session, later_report, later_loc)
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_report, earlier_instance, word_count=64)
    later_unit = _unit(db_session, later_unit_run, later_report, later_instance, word_count=47)

    arun = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    alignment = _alignment(
        db_session, arun, pair, earlier_unit=earlier_unit, later_unit=later_unit,
        status=SemanticUnitAlignmentStatus.MATCHED,
    )
    drun = _decision_run(db_session, pair, arun)
    decision = _decision(db_session, drun, alignment)
    _lexical(db_session, decision, alignment)

    app_comparison_id = uuid.uuid4()
    rows = build_narrative_comparison_rows(db_session, pair, app_comparison_id=app_comparison_id, **_PUB_ARGS)

    assert len(rows) == 1
    row = rows[0]
    assert row.report_comparison_id == app_comparison_id
    assert row.publication_id == _PUB_ARGS["publication_id"]
    assert row.comparison_backend == "SEMANTIC_UNIT"
    assert row.status == ComparisonResponseStatus.RESOLVED.value
    assert row.schedule == "FINANCIAL_PERFORMANCE"
    assert row.unit_key == "gross_margin"
    assert row.alignment_status == SemanticUnitAlignmentStatus.MATCHED.value
    assert row.analytical_mode == AnalyticalMode.LEXICAL_ONLY.value
    assert row.earlier_word_count == 64
    assert row.later_word_count == 47
    assert row.lexical_metrics is not None
    assert row.lexical_metrics["tfidf_cosine"] == 0.747
    assert row.earlier_provenance is not None
    assert row.earlier_provenance["report_id"] == str(earlier_report.id)
    assert row.earlier_provenance["start_page"] == 10


def test_narrative_unresolved_row_is_still_built_never_dropped(db_session):
    """Mirrors the real ACT cfo_conclusion case (0/9 pairs resolve): an
    unresolved comparison is still published, never silently omitted or
    substituted with a legacy result. Since Track 7E.2a
    (docs/7e2a-production-scope-finalization.md), ACT's in-scope narrative
    units span FINANCIAL_PERFORMANCE (cfo_conclusion,
    healthcare_services_review), CORPORATE_GOVERNANCE
    (information_security_governance, governance_policies_processes,
    combined_assurance), and REMUNERATION (remco_chairperson_report,
    remuneration_policy_changes, remuneration_governance) -- all eight
    surface as unresolved rows here (no reports/units set up for any of
    them)."""
    company = _company(db_session, "ACT")
    earlier_report = _report(db_session, company, 2019, "e")
    later_report = _report(db_session, company, 2020, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    rows = build_narrative_comparison_rows(
        db_session, pair, app_comparison_id=uuid.uuid4(), **_PUB_ARGS
    )

    assert len(rows) == 8
    rows_by_unit_key = {row.unit_key: row for row in rows}
    assert set(rows_by_unit_key) == {
        "cfo_conclusion",
        "healthcare_services_review",
        "information_security_governance",
        "governance_policies_processes",
        "combined_assurance",
        "remco_chairperson_report",
        "remuneration_policy_changes",
        "remuneration_governance",
    }
    for row in rows:
        assert row.status == ComparisonResponseStatus.UNRESOLVED_UPSTREAM.value
        assert row.comparison_backend == "SEMANTIC_UNIT"
        assert row.lexical_metrics is None
        assert row.review_reason is not None


def test_narrative_out_of_scope_ticker_returns_no_rows(db_session):
    company = _company(db_session, "KP2")
    earlier_report = _report(db_session, company, 2019, "e")
    later_report = _report(db_session, company, 2020, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    rows = build_narrative_comparison_rows(
        db_session, pair, app_comparison_id=uuid.uuid4(), **_PUB_ARGS
    )
    assert rows == []


def test_structured_resolved_row_built_with_row_column_and_value_change_json(db_session):
    company = _company(db_session, "ACT")
    earlier_report = _report(db_session, company, 2022, "e")
    later_report = _report(db_session, company, 2023, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    earlier_canonical = _canonical_run(db_session, earlier_report)
    later_canonical = _canonical_run(db_session, later_report)
    earlier_page = _canonical_page(db_session, earlier_canonical, earlier_report)
    later_page = _canonical_page(db_session, later_canonical, later_report)
    earlier_block = _canonical_block(db_session, earlier_page)
    later_block = _canonical_block(db_session, later_page)

    family = "total_remuneration_outcomes"
    earlier_extraction = _table_extraction_run(db_session, earlier_report, earlier_canonical, family)
    later_extraction = _table_extraction_run(db_session, later_report, later_canonical, family)
    earlier_table = _structured_table(db_session, earlier_extraction, earlier_report, family, earlier_block)
    later_table = _structured_table(db_session, later_extraction, later_report, family, later_block)
    _footnote(db_session, later_table, later_block)

    arun = _table_alignment_run(db_session, pair, family, earlier_extraction, later_extraction)
    row_alignment = _row_alignment(db_session, arun, earlier_table.rows[0], later_table.rows[0])
    column_alignment = _column_alignment(db_session, arun, earlier_table.columns[0], later_table.columns[0])
    _value_change_event(db_session, arun, row_alignment, column_alignment)

    app_comparison_id = uuid.uuid4()
    rows = build_structured_comparison_rows(db_session, pair, app_comparison_id=app_comparison_id, **_PUB_ARGS)

    # ACT has two in-scope table families; only `total_remuneration_outcomes`
    # has upstream data here, so `ned_remuneration_policy_table` is still
    # published, unresolved.
    assert len(rows) == 2
    by_family = {row.table_family_key: row for row in rows}

    resolved = by_family["total_remuneration_outcomes"]
    assert resolved.report_comparison_id == app_comparison_id
    assert resolved.comparison_backend == "STRUCTURED_TABLE"
    assert resolved.status == ComparisonResponseStatus.RESOLVED.value
    assert len(resolved.row_alignments) == 1
    assert resolved.row_alignments[0]["earlier_row_identity"] == "j smith"
    assert len(resolved.column_alignments) == 1
    assert resolved.column_alignments[0]["normalized_key"] == "total_remuneration"
    assert len(resolved.value_change_events) == 1
    assert resolved.value_change_events[0]["event_type"] == StructuredValueChangeEventType.VALUE_INCREASED.value
    assert resolved.value_change_events[0]["earlier_numeric"] == 100.0
    assert "footnote text" in resolved.footnotes
    assert resolved.earlier_provenance is not None
    assert resolved.earlier_provenance["start_page"] == 105

    unresolved = by_family["ned_remuneration_policy_table"]
    assert unresolved.status == ComparisonResponseStatus.UNRESOLVED_UPSTREAM.value
    assert unresolved.row_alignments == []


def test_structured_out_of_scope_ticker_returns_no_rows(db_session):
    company = _company(db_session, "KP2")
    earlier_report = _report(db_session, company, 2019, "e")
    later_report = _report(db_session, company, 2020, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    rows = build_structured_comparison_rows(
        db_session, pair, app_comparison_id=uuid.uuid4(), **_PUB_ARGS
    )
    assert rows == []


def test_narrative_row_ids_are_deterministic_across_calls(db_session):
    """Mirrors `labels.derive_id`'s idempotent-republish contract: the same
    publication_version + report_pair + unit_key always yields the same row
    id, so rebuilding an unchanged publication_version is an upsert-in-place,
    never a duplicate insert."""
    company = _company(db_session, "BEL")
    earlier_report = _report(db_session, company, 2019, "e")
    later_report = _report(db_session, company, 2020, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    rows_a = build_narrative_comparison_rows(db_session, pair, app_comparison_id=uuid.uuid4(), **_PUB_ARGS)
    rows_b = build_narrative_comparison_rows(db_session, pair, app_comparison_id=uuid.uuid4(), **_PUB_ARGS)

    assert rows_a[0].id == rows_b[0].id
