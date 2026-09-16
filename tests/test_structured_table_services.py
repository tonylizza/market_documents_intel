"""DB-backed orchestration tests for `services.structured_table_reconstruction`
and `services.structured_table_comparison` (Track 7C.4).

Builds the persisted chain directly -- CanonicalExtractionRun ->
CanonicalPage -> CanonicalBlock -> StructuredTableExtractionRun ->
StructuredTable -> rows/columns/cells/footnotes -> ReportPair ->
StructuredTableAlignmentRun -> StructuredRowAlignment/
StructuredColumnAlignment/StructuredValueChangeEvent -- never through
SemanticUnit or the legacy passage pipeline (see
`test_no_semantic_unit_or_passage_dependency`).
"""

from datetime import UTC, datetime

from sqlalchemy import select

from market_documents.models.company import Company
from market_documents.models.enums import (
    CanonicalExtractionStatus,
    MetadataStatus,
    StructuredRowAlignmentStatus,
    StructuredTableAlignmentRunStatus,
    StructuredTableExtractionRunStatus,
)
from market_documents.models.pdf_source import CanonicalBlock, CanonicalExtractionRun, CanonicalPage
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.structured_table import (
    StructuredRowAlignment,
    StructuredTable,
    StructuredTableCell,
    StructuredTableRow,
    StructuredValueChangeEvent,
)
from market_documents.services import structured_table_comparison as stc
from market_documents.services import structured_table_reconstruction as str_


def _company(session) -> Company:
    company = Company(ticker="ACT", company_name="AfroCentric Test")
    session.add(company)
    session.flush()
    return company


def _report(session, company, directory_year) -> Report:
    report = Report(
        company_id=company.id,
        local_path=f"/tmp/ACT-{directory_year}.pdf",
        filename=f"ACT-{directory_year}.pdf",
        sha256=f"{directory_year:064d}",
        directory_year=directory_year,
        page_count=200,
        metadata_status=MetadataStatus.VALIDATED,
    )
    session.add(report)
    session.flush()
    return report


def _canonical_run(session, report) -> CanonicalExtractionRun:
    run = CanonicalExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="x",
        status=CanonicalExtractionStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _page(session, canonical_run, report, page_number) -> CanonicalPage:
    page = CanonicalPage(
        canonical_run_id=canonical_run.id, report_id=report.id, page_number=page_number, width=595.0, height=842.0,
    )
    session.add(page)
    session.flush()
    return page


def _block(session, page, block_order, y0, text) -> CanonicalBlock:
    block = CanonicalBlock(
        page_id=page.id, block_order=block_order, native_type=0, x0=0.0, y0=y0, x1=500.0, y1=y0 + 10.0, raw_text=text,
    )
    session.add(block)
    session.flush()
    return block


def _ned_blocks(session, page):
    _block(session, page, 0, 100.0, "Non-executive Directors' 2020 remuneration \n")
    _block(
        session, page, 1, 150.0,
        "Main Board (annualised retainer fee)\nChairman\n1 329 240\n1 375 763\n3.5\n"
        "Deputy Chairman\n997 713\n1 032 633\n3.5\nMember\n248 188\n256 875\n3.5\n",
    )


def _ned_blocks_later(session, page, current, proposed):
    _block(session, page, 0, 100.0, "Non-executive Directors' 2021 remuneration \n")
    _block(
        session, page, 1, 150.0,
        f"Main Board (annualised retainer fee)\nChairman\n{current}\n{proposed}\n0\n"
        f"Deputy Chairman\n1 317 844\n1 317 844\n0\nMember\n256 875\n305 955\n19.11\n",
    )


def _build_report_with_ned_table(session, company, year, row_block_fn):
    report = _report(session, company, year)
    canonical_run = _canonical_run(session, report)
    page = _page(session, canonical_run, report, page_number=105)
    row_block_fn(session, page)
    return report


def test_reconstruction_ineligible_without_canonical_run(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2020)
    outcome = str_.run_table_reconstruction(db_session, report, "ned_remuneration_policy_table")
    assert outcome.ineligible is True
    assert "canonical extraction" in outcome.ineligible_reason


def test_reconstruction_ineligible_for_unconfigured_ticker(db_session):
    company = Company(ticker="BEL", company_name="Bell Test")
    db_session.add(company)
    db_session.flush()
    report = _report(db_session, company, 2020)
    _canonical_run(db_session, report)
    outcome = str_.run_table_reconstruction(db_session, report, "ned_remuneration_policy_table")
    assert outcome.ineligible is True


def test_reconstruction_persists_table_rows_and_cells(db_session):
    company = _company(db_session)
    report = _build_report_with_ned_table(db_session, company, 2020, _ned_blocks)

    outcome = str_.run_table_reconstruction(db_session, report, "ned_remuneration_policy_table")
    assert outcome.ineligible is False
    assert outcome.skipped is False
    run = outcome.run
    assert run.status == StructuredTableExtractionRunStatus.COMPLETED

    table = db_session.scalar(select(StructuredTable).where(StructuredTable.structured_table_extraction_run_id == run.id))
    assert table is not None
    rows = db_session.scalars(select(StructuredTableRow).where(StructuredTableRow.structured_table_id == table.id)).all()
    assert len(rows) == 3
    chairman = next(r for r in rows if r.source_label == "Chairman")
    cells = db_session.scalars(select(StructuredTableCell).where(StructuredTableCell.structured_table_row_id == chairman.id)).all()
    assert len(cells) == 3
    assert {c.raw_value for c in cells} == {"1 329 240", "1 375 763", "3.5"}
    # Every cell traces to source provenance via its row's source block.
    assert chairman.source_block_id is not None


def test_reconstruction_idempotent_skip_and_force(db_session):
    company = _company(db_session)
    report = _build_report_with_ned_table(db_session, company, 2020, _ned_blocks)

    first = str_.run_table_reconstruction(db_session, report, "ned_remuneration_policy_table")
    second = str_.run_table_reconstruction(db_session, report, "ned_remuneration_policy_table")
    assert second.skipped is True
    assert second.run.id == first.run.id

    third = str_.run_table_reconstruction(db_session, report, "ned_remuneration_policy_table", force=True)
    assert third.skipped is False
    assert third.run.id != first.run.id


def test_comparison_ineligible_without_both_sides_reconstructed(db_session):
    company = _company(db_session)
    earlier = _build_report_with_ned_table(db_session, company, 2020, _ned_blocks)
    later = _report(db_session, company, 2021)
    str_.run_table_reconstruction(db_session, earlier, "ned_remuneration_policy_table")
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id, gap_months=12, is_transition=False)
    db_session.add(pair)
    db_session.flush()

    outcome = stc.run_table_comparison(db_session, pair, "ned_remuneration_policy_table")
    assert outcome.ineligible is True


def test_comparison_matches_rows_and_produces_value_change_events(db_session):
    company = _company(db_session)
    earlier = _build_report_with_ned_table(db_session, company, 2020, _ned_blocks)
    later = _build_report_with_ned_table(
        db_session, company, 2021,
        lambda s, p: _ned_blocks_later(s, p, "1 375 763", "1 445 849"),
    )
    str_.run_table_reconstruction(db_session, earlier, "ned_remuneration_policy_table")
    str_.run_table_reconstruction(db_session, later, "ned_remuneration_policy_table")
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id, gap_months=12, is_transition=False)
    db_session.add(pair)
    db_session.flush()

    outcome = stc.run_table_comparison(db_session, pair, "ned_remuneration_policy_table")
    assert outcome.ineligible is False
    run = outcome.run
    assert run.status == StructuredTableAlignmentRunStatus.COMPLETED

    row_alignments = db_session.scalars(
        select(StructuredRowAlignment).where(StructuredRowAlignment.alignment_run_id == run.id)
    ).all()
    assert len(row_alignments) == 3
    assert all(ra.status == StructuredRowAlignmentStatus.MATCHED for ra in row_alignments)

    events = db_session.scalars(
        select(StructuredValueChangeEvent).where(StructuredValueChangeEvent.alignment_run_id == run.id)
    ).all()
    # 3 rows x 3 columns = 9 value-change events for a fully matched table.
    assert len(events) == 9
    chairman_current_events = [
        e for e in events
        if e.earlier_raw_value == "1 329 240"
    ]
    assert chairman_current_events[0].later_raw_value == "1 375 763"
    assert chairman_current_events[0].absolute_change is not None


def test_comparison_idempotent_skip_and_force(db_session):
    company = _company(db_session)
    earlier = _build_report_with_ned_table(db_session, company, 2020, _ned_blocks)
    later = _build_report_with_ned_table(
        db_session, company, 2021, lambda s, p: _ned_blocks_later(s, p, "1 375 763", "1 445 849")
    )
    str_.run_table_reconstruction(db_session, earlier, "ned_remuneration_policy_table")
    str_.run_table_reconstruction(db_session, later, "ned_remuneration_policy_table")
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id, gap_months=12, is_transition=False)
    db_session.add(pair)
    db_session.flush()

    first = stc.run_table_comparison(db_session, pair, "ned_remuneration_policy_table")
    second = stc.run_table_comparison(db_session, pair, "ned_remuneration_policy_table")
    assert second.skipped is True
    assert second.run.id == first.run.id

    third = stc.run_table_comparison(db_session, pair, "ned_remuneration_policy_table", force=True)
    assert third.skipped is False
    assert third.run.id != first.run.id


def test_no_semantic_unit_or_passage_dependency():
    for module in (str_, stc):
        imported_names = {getattr(v, "__name__", "") for v in vars(module).values()}
        assert not any("SemanticUnit" in name or "Passage" in name for name in imported_names)
