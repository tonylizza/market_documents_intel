from datetime import UTC, datetime

from market_documents.models.company import Company
from market_documents.models.enums import BlockType, ExtractionQuality, ExtractionStatus, MetadataStatus
from market_documents.models.extraction import ExtractionRun, NarrativeDocument, Page, TextBlock
from market_documents.models.report import Report
from market_documents.services import passage_segmentation as ps
from market_documents.services.narrative_construction import build_narrative_text, compute_content_hash
from market_documents.services.segmentation_audit import build_segmentation_audit_rows


def _company(db_session, ticker="AUD") -> Company:
    company = Company(ticker=ticker, company_name="Audit Test Co")
    db_session.add(company)
    db_session.flush()
    return company


def _report(db_session, company: Company, year: int, path_suffix: str) -> Report:
    local_path = f"data/raw/{company.ticker}/{year}/{path_suffix}.pdf"
    report = Report(
        company_id=company.id,
        local_path=local_path,
        filename=f"{path_suffix}.pdf",
        sha256=compute_content_hash(local_path),
        directory_year=year,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()
    return report


def _words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def _segmentable_report(db_session, ticker="AUD"):
    company = _company(db_session, ticker)
    report = _report(db_session, company, 2023, "annual")
    run = ExtractionRun(
        report_id=report.id,
        extractor_name="test",
        extractor_version="1",
        configuration_hash="test-hash",
        status=ExtractionStatus.COMPLETED,
        extraction_quality=ExtractionQuality.GOOD,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        encrypted_pdf_handled=False,
    )
    db_session.add(run)
    db_session.flush()

    page = Page(
        extraction_run_id=run.id,
        report_id=report.id,
        page_number=1,
        raw_text="text",
        cleaned_text="text",
        character_count=4,
        word_count=1,
        block_count=2,
        native_text_available=True,
        suspected_image_only=False,
        extraction_quality=ExtractionQuality.GOOD,
    )
    db_session.add(page)
    db_session.flush()

    db_session.add(
        TextBlock(
            extraction_run_id=run.id,
            page_id=page.id,
            report_id=report.id,
            block_index=0,
            reading_order=0,
            raw_text="Overview",
            cleaned_text="Overview",
            block_type=BlockType.HEADING_CANDIDATE,
        )
    )
    db_session.add(
        TextBlock(
            extraction_run_id=run.id,
            page_id=page.id,
            report_id=report.id,
            block_index=1,
            reading_order=1,
            raw_text=_words(80),
            cleaned_text=_words(80),
            block_type=BlockType.PARAGRAPH,
        )
    )
    db_session.flush()

    narrative_text = build_narrative_text(db_session, run.id)
    narrative = NarrativeDocument(
        extraction_run_id=run.id,
        report_id=report.id,
        cleaned_text=narrative_text,
        word_count=len(narrative_text.split()),
        content_hash=compute_content_hash(narrative_text),
    )
    db_session.add(narrative)
    db_session.flush()
    return report


def test_audit_row_for_segmented_report(db_session):
    report = _segmentable_report(db_session)
    ps.segment_report(db_session, report)

    rows = build_segmentation_audit_rows(db_session)
    row = next(r for r in rows if r.report_id == str(report.id))

    assert row.ticker == "AUD"
    assert row.segmentation_run_id is not None
    assert row.passage_count == 1
    assert row.run_status == "COMPLETED"
    assert row.heading_associated_passage_count == 1


def test_audit_row_for_unsegmented_report(db_session):
    company = _company(db_session, "NOSEG")
    report = _report(db_session, company, 2023, "annual")

    rows = build_segmentation_audit_rows(db_session)
    row = next(r for r in rows if r.report_id == str(report.id))

    assert row.segmentation_run_id is None
    assert row.passage_count is None
    assert row.run_status is None
