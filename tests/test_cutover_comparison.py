"""Tests for Track 7C.6's `services.cutover_comparison` -- normalized,
discriminated comparison responses for the exact scoped-cutover requests.

Builds minimal fixtures directly via the ORM (not through either
pipeline's service layer), mirroring the pattern in
`tests/test_shadow_evaluation.py` and `tests/test_structured_table_services.py`.
"""

from datetime import UTC, datetime
import hashlib

from sqlalchemy import select

from market_documents.models.analytical_comparison import (
    AnalyticalDecision,
    AnalyticalDecisionRun,
    LexicalUnitComparison,
)
from market_documents.models.company import Company
from market_documents.models.enums import (
    AlignmentConfidence,
    AnalyticalDecisionRunStatus,
    AnalyticalMode,
    BoundaryConfidence,
    CanonicalExtractionStatus,
    ComparisonBackend,
    ComparisonResponseStatus,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    NormalizedSchedule,
    ScheduleLocalizationRunStatus,
    ScheduleLocalizationStatus,
    SemanticUnitAlignmentRunStatus,
    SemanticUnitAlignmentStatus,
    SemanticUnitBoundaryStatus,
    SemanticUnitBoundaryStrategy,
    SemanticUnitRunStatus,
    SemanticUnitType,
    StructuredColumnAlignmentStatus,
    StructuredComparabilityStatus,
    StructuredRowAlignmentStatus,
    StructuredRowIdentityType,
    StructuredTableAlignmentRunStatus,
    StructuredTableExtractionRunStatus,
    StructuredTableReconstructionStatus,
    StructuredTableShape,
    StructuredValueChangeEventType,
)
from market_documents.models.extraction import ExtractionRun
from market_documents.models.pdf_source import CanonicalBlock, CanonicalExtractionRun, CanonicalPage
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.schedule import ScheduleInstance, ScheduleLocalizationRun
from market_documents.models.semantic_unit import SemanticUnit, SemanticUnitRun
from market_documents.models.semantic_unit_alignment import SemanticUnitAlignment, SemanticUnitAlignmentRun
from market_documents.models.structured_table import (
    StructuredColumnAlignment,
    StructuredRowAlignment,
    StructuredTable,
    StructuredTableAlignmentRun,
    StructuredTableColumn,
    StructuredTableExtractionRun,
    StructuredTableFootnote,
    StructuredTableRow,
    StructuredValueChangeEvent,
)
from market_documents.services.comparison_routing import ComparisonPathRouter
from market_documents.services.cutover_comparison import (
    LegacyComparisonResponse,
    NarrativeComparisonResponse,
    StructuredComparisonResponse,
    get_narrative_comparison,
    get_structured_comparison,
)

FP = NormalizedSchedule.FINANCIAL_PERFORMANCE
ENABLED = ComparisonPathRouter(cutover_enabled=True)
DISABLED = ComparisonPathRouter(cutover_enabled=False)


# --- fixtures ---------------------------------------------------------------------


def _company(session, ticker="BEL") -> Company:
    company = Company(ticker=ticker, company_name=f"{ticker} Cutover Test")
    session.add(company)
    session.flush()
    return company


def _report(session, company, year, suffix="r") -> Report:
    report = Report(
        company_id=company.id,
        local_path=f"data/raw/{company.ticker}/{year}/{suffix}.pdf",
        filename=f"{suffix}.pdf",
        sha256=f"{company.ticker}-{suffix}-{year}",
        directory_year=year,
        metadata_status=MetadataStatus.VALIDATED,
    )
    session.add(report)
    session.flush()
    return report


def _pair(session, company, earlier, later) -> ReportPair:
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id, gap_months=12)
    session.add(pair)
    session.flush()
    return pair


def _extraction_run(session, report) -> ExtractionRun:
    run = ExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="x",
        status=ExtractionStatus.COMPLETED, extraction_quality=ExtractionQuality.GOOD,
        started_at=datetime.now(UTC), completed_at=datetime.now(UTC), encrypted_pdf_handled=False,
    )
    session.add(run)
    session.flush()
    return run


def _localization_run(session, report) -> ScheduleLocalizationRun:
    extraction_run = _extraction_run(session, report)
    run = ScheduleLocalizationRun(
        report_id=report.id, extraction_run_id=extraction_run.id, schedule=FP, algorithm_version="1",
        configuration_hash="x", status=ScheduleLocalizationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _schedule_instance(session, loc_run, report) -> ScheduleInstance:
    instance = ScheduleInstance(
        schedule_localization_run_id=loc_run.id, report_id=report.id, schedule=FP,
        status=ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY, heading_text="Gross Margin", start_page=10,
        end_page=10, boundary_confidence=BoundaryConfidence.HIGH,
    )
    session.add(instance)
    session.flush()
    return instance


def _unit_run(session, report, loc_run, *, clean=True) -> SemanticUnitRun:
    run = SemanticUnitRun(
        report_id=report.id, schedule_localization_run_id=loc_run.id, schedule=FP, algorithm_version="1",
        configuration_hash="x",
        status=SemanticUnitRunStatus.COMPLETED if clean else SemanticUnitRunStatus.COMPLETED_WITH_WARNINGS,
        completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _unit(session, unit_run, report, instance, unit_key="gross_margin", word_count=20, text=None) -> SemanticUnit:
    unit = SemanticUnit(
        semantic_unit_run_id=unit_run.id, report_id=report.id, schedule_instance_id=instance.id, unit_key=unit_key,
        unit_type=SemanticUnitType.HEADED_NARRATIVE_UNIT, source_heading="Gross Margin", start_page=10,
        boundary_strategy=SemanticUnitBoundaryStrategy.ANCHOR_SENTENCE, boundary_status=SemanticUnitBoundaryStatus.RESOLVED,
        boundary_confidence=BoundaryConfidence.HIGH, end_page=10, source_text=text or ("text " * word_count).strip(),
        word_count=word_count,
    )
    session.add(unit)
    session.flush()
    return unit


def _alignment_run(session, pair, earlier_unit_run, later_unit_run) -> SemanticUnitAlignmentRun:
    run = SemanticUnitAlignmentRun(
        report_pair_id=pair.id, earlier_semantic_unit_run_id=earlier_unit_run.id, later_semantic_unit_run_id=later_unit_run.id,
        schedule=FP, algorithm_version="1", configuration_hash="x",
        status=SemanticUnitAlignmentRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _alignment(session, arun, pair, *, earlier_unit=None, later_unit=None, status, evidence="test") -> SemanticUnitAlignment:
    alignment = SemanticUnitAlignment(
        alignment_run_id=arun.id, report_pair_id=pair.id,
        earlier_semantic_unit_id=earlier_unit.id if earlier_unit else None,
        later_semantic_unit_id=later_unit.id if later_unit else None,
        status=status, confidence=AlignmentConfidence.HIGH, evidence=evidence,
    )
    session.add(alignment)
    session.flush()
    return alignment


def _decision_run(session, pair, arun) -> AnalyticalDecisionRun:
    run = AnalyticalDecisionRun(
        alignment_run_id=arun.id, report_pair_id=pair.id, schedule=FP, algorithm_version="1",
        configuration_hash="x", status=AnalyticalDecisionRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _decision(session, drun, alignment, *, mode=AnalyticalMode.LEXICAL_ONLY) -> AnalyticalDecision:
    decision = AnalyticalDecision(
        decision_run_id=drun.id, semantic_unit_alignment_id=alignment.id, analytical_mode=mode,
        confidence=AlignmentConfidence.HIGH, reason="test",
    )
    session.add(decision)
    session.flush()
    return decision


def _lexical(session, decision, alignment, *, earlier_wc=64, later_wc=47) -> LexicalUnitComparison:
    lc = LexicalUnitComparison(
        analytical_decision_id=decision.id, semantic_unit_alignment_id=alignment.id,
        tfidf_cosine=0.747, unigram_jaccard=0.5, bigram_jaccard=0.4, edit_similarity=0.6, sequence_similarity=0.6,
        earlier_word_count=earlier_wc, later_word_count=later_wc, word_count_change=later_wc - earlier_wc,
        word_count_change_pct=(later_wc - earlier_wc) / earlier_wc,
    )
    session.add(lc)
    session.flush()
    return lc


# --- structured-table fixtures ------------------------------------------------


def _canonical_run(session, report) -> CanonicalExtractionRun:
    run = CanonicalExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="x",
        status=CanonicalExtractionStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _canonical_page(session, canonical_run, report, page_number=105) -> CanonicalPage:
    page = CanonicalPage(canonical_run_id=canonical_run.id, report_id=report.id, page_number=page_number, width=595.0, height=842.0)
    session.add(page)
    session.flush()
    return page


def _canonical_block(session, page, order=0, text="row text") -> CanonicalBlock:
    block = CanonicalBlock(page_id=page.id, block_order=order, native_type=0, x0=0.0, y0=100.0, x1=500.0, y1=110.0, raw_text=text)
    session.add(block)
    session.flush()
    return block


def _table_extraction_run(session, report, canonical_run, table_family_key) -> StructuredTableExtractionRun:
    run = StructuredTableExtractionRun(
        report_id=report.id, canonical_run_id=canonical_run.id, table_family_key=table_family_key,
        algorithm_version="1", configuration_hash="x", status=StructuredTableExtractionRunStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _structured_table(session, extraction_run, report, table_family_key, block) -> StructuredTable:
    table = StructuredTable(
        structured_table_extraction_run_id=extraction_run.id, report_id=report.id, table_family_key=table_family_key,
        schedule=NormalizedSchedule.REMUNERATION, source_heading="Total remuneration outcomes",
        start_page=105, end_page=105, table_shape=StructuredTableShape.RECTANGULAR_MATRIX,
        row_identity_type=StructuredRowIdentityType.PERSON, analytical_mode=AnalyticalMode.STRUCTURED_COMPARISON_PREFERRED,
        reconstruction_status=StructuredTableReconstructionStatus.CLEAN, reconstruction_confidence=AlignmentConfidence.HIGH,
    )
    session.add(table)
    session.flush()
    row = StructuredTableRow(
        structured_table_id=table.id, position=0, source_label="J Smith", normalized_identity="j smith",
        source_block_id=block.id,
    )
    session.add(row)
    column = StructuredTableColumn(
        structured_table_id=table.id, position=0, source_label="Total remuneration", normalized_key="total_remuneration",
        is_restated=False,
    )
    session.add(column)
    session.flush()
    return table


def _footnote(session, table, block) -> StructuredTableFootnote:
    fn = StructuredTableFootnote(structured_table_id=table.id, marker="1", text="footnote text", page=105, source_block_id=block.id)
    session.add(fn)
    session.flush()
    return fn


def _table_alignment_run(session, pair, table_family_key, earlier_run, later_run) -> StructuredTableAlignmentRun:
    run = StructuredTableAlignmentRun(
        report_pair_id=pair.id, table_family_key=table_family_key,
        earlier_structured_table_extraction_run_id=earlier_run.id, later_structured_table_extraction_run_id=later_run.id,
        algorithm_version="1", configuration_hash="x", status=StructuredTableAlignmentRunStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _row_alignment(session, arun, earlier_row, later_row) -> StructuredRowAlignment:
    ra = StructuredRowAlignment(
        alignment_run_id=arun.id, earlier_structured_table_row_id=earlier_row.id, later_structured_table_row_id=later_row.id,
        status=StructuredRowAlignmentStatus.MATCHED, confidence=AlignmentConfidence.HIGH, evidence="matched",
    )
    session.add(ra)
    session.flush()
    return ra


def _column_alignment(session, arun, earlier_col, later_col) -> StructuredColumnAlignment:
    ca = StructuredColumnAlignment(
        alignment_run_id=arun.id, earlier_structured_table_column_id=earlier_col.id, later_structured_table_column_id=later_col.id,
        status=StructuredColumnAlignmentStatus.MATCHED, comparability_status=StructuredComparabilityStatus.DIRECTLY_COMPARABLE,
        confidence=AlignmentConfidence.HIGH, evidence="matched",
    )
    session.add(ca)
    session.flush()
    return ca


def _value_change_event(session, arun, row_alignment, column_alignment) -> StructuredValueChangeEvent:
    ev = StructuredValueChangeEvent(
        alignment_run_id=arun.id, row_alignment_id=row_alignment.id, column_alignment_id=column_alignment.id,
        event_type=StructuredValueChangeEventType.VALUE_INCREASED, earlier_raw_value="100", later_raw_value="120",
        earlier_numeric=100.0, later_numeric=120.0, absolute_change=20.0, pct_change=0.2,
    )
    session.add(ev)
    session.flush()
    return ev


# --- narrative: resolved / MATCHED -------------------------------------------------


def test_narrative_matched_returns_lexical_comparison_and_provenance(db_session):
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
    alignment = _alignment(db_session, arun, pair, earlier_unit=earlier_unit, later_unit=later_unit, status=SemanticUnitAlignmentStatus.MATCHED)
    drun = _decision_run(db_session, pair, arun)
    decision = _decision(db_session, drun, alignment)
    _lexical(db_session, decision, alignment)

    response = get_narrative_comparison(db_session, pair, FP, "gross_margin", router=ENABLED)

    assert isinstance(response, NarrativeComparisonResponse)
    assert response.comparison_backend == ComparisonBackend.SEMANTIC_UNIT
    assert response.status == ComparisonResponseStatus.RESOLVED
    assert response.alignment_status == SemanticUnitAlignmentStatus.MATCHED
    assert response.analytical_mode == AnalyticalMode.LEXICAL_ONLY
    assert response.lexical_metrics is not None
    assert response.lexical_metrics.tfidf_cosine == 0.747
    assert response.earlier_word_count == 64
    assert response.later_word_count == 47
    # Provenance (Section 9/F): page + source-block id + source excerpt.
    assert response.earlier_provenance is not None
    assert response.earlier_provenance.start_page == 10
    assert response.earlier_provenance.directory_year == 2018
    assert response.earlier_provenance.source_excerpt is not None
    assert response.later_provenance is not None


# --- narrative: unresolved upstream, no silent legacy fallback ---------------------


def test_narrative_no_alignment_run_is_unresolved_upstream(db_session):
    company = _company(db_session, "BEL")
    earlier_report = _report(db_session, company, 2019, "e")
    later_report = _report(db_session, company, 2020, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    response = get_narrative_comparison(db_session, pair, FP, "gross_margin", router=ENABLED)

    assert isinstance(response, NarrativeComparisonResponse)
    assert response.status == ComparisonResponseStatus.UNRESOLVED_UPSTREAM
    assert response.comparison_backend == ComparisonBackend.SEMANTIC_UNIT
    assert response.review_reason is not None


def test_narrative_alignment_unresolved_upstream_is_surfaced_explicitly(db_session):
    company = _company(db_session, "BEL")
    earlier_report = _report(db_session, company, 2019, "e")
    later_report = _report(db_session, company, 2020, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    earlier_loc = _localization_run(db_session, earlier_report)
    later_loc = _localization_run(db_session, later_report)
    earlier_instance = _schedule_instance(db_session, earlier_loc, earlier_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_loc)
    later_unit_run = _unit_run(db_session, later_report, later_loc, clean=False)
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_report, earlier_instance)

    arun = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    _alignment(
        db_session, arun, pair, earlier_unit=earlier_unit, later_unit=None,
        status=SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, evidence="later run completed with warnings",
    )

    response = get_narrative_comparison(db_session, pair, FP, "gross_margin", router=ENABLED)

    assert isinstance(response, NarrativeComparisonResponse)
    assert response.status == ComparisonResponseStatus.UNRESOLVED_UPSTREAM
    assert response.alignment_status == SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM
    # Never silently satisfied by a legacy result: no backend switch to
    # LEGACY_PASSAGE occurs here even though nothing resolved.
    assert response.comparison_backend == ComparisonBackend.SEMANTIC_UNIT


def test_narrative_ambiguous_alignment_is_surfaced_explicitly(db_session):
    company = _company(db_session, "ACT")
    earlier_report = _report(db_session, company, 2021, "e")
    later_report = _report(db_session, company, 2022, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    earlier_loc = _localization_run(db_session, earlier_report)
    later_loc = _localization_run(db_session, later_report)
    earlier_instance = _schedule_instance(db_session, earlier_loc, earlier_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_loc)
    later_unit_run = _unit_run(db_session, later_report, later_loc)
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_report, earlier_instance, unit_key="cfo_conclusion")

    arun = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    _alignment(
        db_session, arun, pair, earlier_unit=earlier_unit, later_unit=None,
        status=SemanticUnitAlignmentStatus.AMBIGUOUS, evidence="2 later units match normalized heading",
    )

    response = get_narrative_comparison(db_session, pair, FP, "cfo_conclusion", router=ENABLED)
    assert response.status == ComparisonResponseStatus.AMBIGUOUS


def test_narrative_missing_decision_is_review_required(db_session):
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
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_report, earlier_instance)
    later_unit = _unit(db_session, later_unit_run, later_report, later_instance)

    arun = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    _alignment(db_session, arun, pair, earlier_unit=earlier_unit, later_unit=later_unit, status=SemanticUnitAlignmentStatus.MATCHED)
    # No AnalyticalDecisionRun created at all.

    response = get_narrative_comparison(db_session, pair, FP, "gross_margin", router=ENABLED)
    assert response.status == ComparisonResponseStatus.REVIEW_REQUIRED


# --- structured: resolved -----------------------------------------------------


def test_structured_resolved_returns_row_column_and_value_change_events(db_session):
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

    response = get_structured_comparison(db_session, pair, family, router=ENABLED)

    assert isinstance(response, StructuredComparisonResponse)
    assert response.comparison_backend == ComparisonBackend.STRUCTURED_TABLE
    assert response.status == ComparisonResponseStatus.RESOLVED
    assert len(response.row_alignments) == 1
    assert response.row_alignments[0].earlier_row_identity == "j smith"
    assert len(response.column_alignments) == 1
    assert response.column_alignments[0].normalized_key == "total_remuneration"
    assert len(response.value_change_events) == 1
    event = response.value_change_events[0]
    assert event.event_type == StructuredValueChangeEventType.VALUE_INCREASED
    assert event.earlier_numeric == 100.0
    assert event.later_numeric == 120.0
    assert "footnote text" in response.footnotes
    # Provenance.
    assert response.earlier_provenance is not None
    assert response.earlier_provenance.start_page == 105
    assert len(response.earlier_provenance.source_block_ids) == 1


def test_structured_no_alignment_run_is_unresolved_upstream(db_session):
    company = _company(db_session, "ACT")
    earlier_report = _report(db_session, company, 2016, "e")
    later_report = _report(db_session, company, 2017, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    response = get_structured_comparison(db_session, pair, "ned_remuneration_policy_table", router=ENABLED)
    assert isinstance(response, StructuredComparisonResponse)
    assert response.status == ComparisonResponseStatus.UNRESOLVED_UPSTREAM
    assert response.comparison_backend == ComparisonBackend.STRUCTURED_TABLE


# --- legacy preservation: out-of-scope requests never touch the new pipeline -------


def test_unsupported_ticker_returns_legacy_response(db_session):
    company = _company(db_session, "KP2")
    earlier_report = _report(db_session, company, 2019, "e")
    later_report = _report(db_session, company, 2020, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    response = get_narrative_comparison(db_session, pair, FP, "gross_margin", router=ENABLED)
    assert isinstance(response, LegacyComparisonResponse)
    assert response.comparison_backend == ComparisonBackend.LEGACY_PASSAGE
    assert response.status == ComparisonResponseStatus.NOT_AVAILABLE


def test_cutover_disabled_returns_legacy_response_for_in_scope_unit(db_session):
    company = _company(db_session, "BEL")
    earlier_report = _report(db_session, company, 2018, "e")
    later_report = _report(db_session, company, 2019, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    response = get_narrative_comparison(db_session, pair, FP, "gross_margin", router=DISABLED)
    assert isinstance(response, LegacyComparisonResponse)
    assert response.comparison_backend == ComparisonBackend.LEGACY_PASSAGE
