"""DB-backed orchestration tests for `services.semantic_unit_extraction`
(Track 7C.1), focused on Track 7D.3's supporting-spans page-range fix
(`semantic_unit_extraction.py` ALGORITHM_VERSION 1.4.0).

Builds the full persisted chain -- ExtractionRun -> Page/TextBlock ->
ScheduleLocalizationRun -> ScheduleInstance(+ supporting spans) -- directly,
since `run_extraction` reads only this persisted output.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from market_documents.models.company import Company
from market_documents.models.enums import (
    BlockType,
    BoundaryConfidence,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    NormalizedSchedule,
    ScheduleLocalizationRunStatus,
    ScheduleLocalizationStatus,
    SemanticUnitBoundaryStatus,
    SemanticUnitRunStatus,
)
from market_documents.models.extraction import ExtractionRun, Page, TextBlock
from market_documents.models.report import Report
from market_documents.models.schedule import ScheduleInstance, ScheduleInstanceSupportingSpan, ScheduleLocalizationRun
from market_documents.models.semantic_unit import SemanticUnit
from market_documents.services import semantic_unit_extraction as sue

SCHEDULE = NormalizedSchedule.CORPORATE_GOVERNANCE


def _company(session, ticker="BEL") -> Company:
    company = Company(ticker=ticker, company_name="Test Co")
    session.add(company)
    session.flush()
    return company


def _report(session, company, directory_year=2019) -> Report:
    report = Report(
        company_id=company.id,
        local_path=f"/tmp/{company.ticker}-{directory_year}.pdf",
        filename=f"{company.ticker}-{directory_year}.pdf",
        sha256=f"{directory_year:064d}",
        directory_year=directory_year,
        page_count=20,
        metadata_status=MetadataStatus.VALIDATED,
    )
    session.add(report)
    session.flush()
    return report


def _extraction_run(session, report) -> ExtractionRun:
    run = ExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="x",
        status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _page(session, extraction_run, report, page_number) -> Page:
    page = Page(
        extraction_run_id=extraction_run.id, report_id=report.id, page_number=page_number,
        raw_text="", extraction_quality=ExtractionQuality.GOOD, native_text_available=True,
    )
    session.add(page)
    session.flush()
    return page


def _block(session, extraction_run, page, report, order, text, block_type=BlockType.PARAGRAPH) -> TextBlock:
    block = TextBlock(
        extraction_run_id=extraction_run.id, page_id=page.id, report_id=report.id,
        block_index=order, reading_order=order, raw_text=text, cleaned_text=text,
        block_type=block_type, is_repeated_header=False, is_repeated_footer=False,
        excluded_from_narrative=False,
    )
    session.add(block)
    session.flush()
    return block


def _localization_run(session, report, extraction_run) -> ScheduleLocalizationRun:
    run = ScheduleLocalizationRun(
        report_id=report.id, extraction_run_id=extraction_run.id, schedule=SCHEDULE,
        algorithm_version="1", configuration_hash="x",
        status=ScheduleLocalizationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def test_unit_on_supporting_span_page_is_found_after_range_widening_fix(db_session):
    """Regression for the exact BEL 2018/2019 CORPORATE_GOVERNANCE defect:
    a FOUND_PRIMARY_AND_SUPPORTING instance's primary span covers only its
    first page (10-10); the real subsection heading and its narrative sit on
    page 12, inside a supporting span (10-12) the pre-7D.3 code never
    searched. `run_extraction` must find it after the widening fix."""
    company = _company(session=db_session)
    report = _report(db_session, company)
    extraction_run = _extraction_run(db_session, report)

    page10 = _page(db_session, extraction_run, report, 10)
    _block(db_session, extraction_run, page10, report, 0, "Corporate governance report", BlockType.HEADING_CANDIDATE)

    page11 = _page(db_session, extraction_run, report, 11)
    _block(db_session, extraction_run, page11, report, 0, "Corporate governance report continued", BlockType.HEADING_CANDIDATE)

    page12 = _page(db_session, extraction_run, report, 12)
    _block(db_session, extraction_run, page12, report, 0, "Board composition and diversity", BlockType.HEADING_CANDIDATE)
    _block(db_session, extraction_run, page12, report, 1, "The board comprises a diverse mix of skills and tenure.")
    _block(db_session, extraction_run, page12, report, 2, "Roles and responsibilities", BlockType.HEADING_CANDIDATE)

    localization_run = _localization_run(db_session, report, extraction_run)
    instance = ScheduleInstance(
        schedule_localization_run_id=localization_run.id, report_id=report.id, schedule=SCHEDULE,
        status=ScheduleLocalizationStatus.FOUND_PRIMARY_AND_SUPPORTING, heading_text="Corporate governance report",
        start_page=10, end_page=10, boundary_confidence=BoundaryConfidence.HIGH,
    )
    db_session.add(instance)
    db_session.flush()
    db_session.add(
        ScheduleInstanceSupportingSpan(
            schedule_instance_id=instance.id, heading_text="Corporate governance report continued",
            start_page=11, end_page=12,
        )
    )
    db_session.flush()

    outcome = sue.run_extraction(db_session, report, SCHEDULE)

    assert outcome.ineligible is False
    run = outcome.run
    assert run.status == SemanticUnitRunStatus.COMPLETED

    units = db_session.scalars(select(SemanticUnit).where(SemanticUnit.semantic_unit_run_id == run.id)).all()
    assert len(units) == 1
    unit = units[0]
    assert unit.unit_key == "board_composition_diversity"
    assert unit.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert unit.start_page == 12
    assert "diverse mix of skills" in unit.source_text
