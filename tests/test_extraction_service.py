from datetime import UTC, datetime, timedelta

import fitz
import pytest
from pypdf import PdfWriter
from sqlalchemy import select

from market_documents.models.company import Company
from market_documents.models.enums import ExtractionQuality, ExtractionStatus, MetadataStatus
from market_documents.models.extraction import ExtractionRun, Page, TextBlock
from market_documents.models.report import Report
from market_documents.services import extraction

GOOD_PARAGRAPH = (
    "The group delivered a resilient operating performance during the "
    "period under review, with revenue growth recorded across all "
    "reporting segments and continued margin discipline maintained "
    "despite a challenging macroeconomic environment. Management remains "
    "confident in the underlying strategy and the medium-term outlook "
    "for the business as conditions normalise. "
) * 2


def _build_report_pdf(path, page_count: int = 6) -> None:
    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page(width=400, height=600)
        page.insert_textbox(fitz.Rect(50, 50, 350, 550), GOOD_PARAGRAPH, fontsize=10)
    doc.save(str(path))
    doc.close()


def _build_corrupt_pdf(path) -> None:
    path.write_bytes(b"not a real pdf")


def _build_encrypted_pdf(path, page_count: int = 6) -> None:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=400, height=600)
    writer.encrypt(user_password="", owner_password="owner-secret", algorithm="AES-256")
    with path.open("wb") as f:
        writer.write(f)


def _company(session, ticker="TST") -> Company:
    company = Company(ticker=ticker, company_name="Test Co")
    session.add(company)
    session.flush()
    return company


def _report(session, company, path, **overrides) -> Report:
    defaults = dict(
        company_id=company.id,
        local_path=str(path),
        filename=path.name,
        sha256=overrides.pop("sha256", "a" * 64),
        directory_year=2024,
        page_count=6,
        metadata_status=MetadataStatus.VALIDATED,
    )
    defaults.update(overrides)
    report = Report(**defaults)
    session.add(report)
    session.flush()
    return report


def test_extract_report_completes_with_good_quality(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=6)
    report = _report(db_session, company, pdf_path)

    outcome = extraction.extract_report(db_session, report)

    assert outcome.skipped is False
    run = outcome.run
    assert run.status in (ExtractionStatus.COMPLETED, ExtractionStatus.COMPLETED_WITH_WARNINGS)
    assert run.extraction_quality == ExtractionQuality.GOOD
    assert run.processed_page_count == 6
    assert run.expected_page_count == 6
    assert run.total_word_count > 0

    pages = db_session.scalars(select(Page).where(Page.extraction_run_id == run.id)).all()
    assert len(pages) == 6
    blocks = db_session.scalars(select(TextBlock).where(TextBlock.extraction_run_id == run.id)).all()
    assert len(blocks) > 0
    assert run.narrative_document is not None
    assert run.narrative_document.word_count > 0


def test_text_block_provenance_traces_to_report_run_and_page(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=2)
    report = _report(db_session, company, pdf_path, page_count=2)

    outcome = extraction.extract_report(db_session, report)
    run = outcome.run

    blocks = db_session.scalars(select(TextBlock).where(TextBlock.extraction_run_id == run.id)).all()
    assert blocks
    for block in blocks:
        assert block.report_id == report.id
        assert block.extraction_run_id == run.id
        page = db_session.get(Page, block.page_id)
        assert page.extraction_run_id == run.id
        assert page.report_id == report.id


def test_extract_report_skips_identical_successful_extraction(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=3)
    report = _report(db_session, company, pdf_path, page_count=3)

    first = extraction.extract_report(db_session, report)
    second = extraction.extract_report(db_session, report)

    assert first.skipped is False
    assert second.skipped is True
    assert second.run.id == first.run.id

    all_runs = db_session.scalars(
        select(ExtractionRun).where(ExtractionRun.report_id == report.id)
    ).all()
    assert len(all_runs) == 1


def test_extract_report_force_creates_new_run(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=3)
    report = _report(db_session, company, pdf_path, page_count=3)

    first = extraction.extract_report(db_session, report)
    second = extraction.extract_report(db_session, report, force=True)

    assert second.skipped is False
    assert second.run.id != first.run.id

    all_runs = db_session.scalars(
        select(ExtractionRun).where(ExtractionRun.report_id == report.id)
    ).all()
    assert len(all_runs) == 2


def test_extract_report_changed_configuration_creates_new_run(db_session, tmp_path, monkeypatch):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=3)
    report = _report(db_session, company, pdf_path, page_count=3)

    first = extraction.extract_report(db_session, report)

    monkeypatch.setattr(extraction, "_extractor_version", lambda: "999.0.0-different")
    second = extraction.extract_report(db_session, report)

    assert second.skipped is False
    assert second.run.id != first.run.id
    assert second.run.configuration_hash != first.run.configuration_hash


def test_extract_report_persists_failure_without_partial_rows(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "corrupt.pdf"
    _build_corrupt_pdf(pdf_path)
    report = _report(db_session, company, pdf_path, page_count=0, metadata_status=MetadataStatus.NEEDS_REVIEW)

    outcome = extraction.extract_report(db_session, report)

    run = outcome.run
    assert run.status == ExtractionStatus.FAILED
    assert run.error_message is not None

    pages = db_session.scalars(select(Page).where(Page.extraction_run_id == run.id)).all()
    blocks = db_session.scalars(select(TextBlock).where(TextBlock.extraction_run_id == run.id)).all()
    assert pages == []
    assert blocks == []


def test_failed_run_never_becomes_current_successful_extraction(db_session, tmp_path):
    company = _company(db_session)
    good_path = tmp_path / "good.pdf"
    _build_report_pdf(good_path, page_count=3)
    report = _report(db_session, company, good_path, page_count=3)

    first = extraction.extract_report(db_session, report)
    assert first.run.status != ExtractionStatus.FAILED

    # Point local_path at a corrupt file and force a retry -- it must fail
    # without disturbing the prior successful run's standing.
    report.local_path = str(tmp_path / "corrupt.pdf")
    _build_corrupt_pdf(tmp_path / "corrupt.pdf")
    db_session.flush()

    second = extraction.extract_report(db_session, report, force=True)
    assert second.run.status == ExtractionStatus.FAILED

    current = extraction.get_current_extraction_run(db_session, report.id)
    assert current.id == first.run.id


def test_get_current_extraction_run_none_when_only_failures(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "corrupt.pdf"
    _build_corrupt_pdf(pdf_path)
    report = _report(db_session, company, pdf_path, page_count=0, metadata_status=MetadataStatus.NEEDS_REVIEW)

    extraction.extract_report(db_session, report)

    assert extraction.get_current_extraction_run(db_session, report.id) is None


def test_get_current_extraction_run_picks_latest_completed_at(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=2)
    report = _report(db_session, company, pdf_path, page_count=2)

    older = extraction.extract_report(db_session, report).run
    newer = extraction.extract_report(db_session, report, force=True).run

    # Guard against both runs landing in the same microsecond.
    older.completed_at = datetime.now(UTC) - timedelta(hours=1)
    newer.completed_at = datetime.now(UTC)
    db_session.flush()

    current = extraction.get_current_extraction_run(db_session, report.id)
    assert current.id == newer.id


def test_extract_report_records_encrypted_pdf_handling(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "encrypted.pdf"
    _build_encrypted_pdf(pdf_path, page_count=2)
    report = _report(db_session, company, pdf_path, page_count=2)

    outcome = extraction.extract_report(db_session, report)

    assert outcome.run.encrypted_pdf_handled is True
    assert outcome.run.status != ExtractionStatus.FAILED


def test_extract_eligible_reports_processes_only_eligible_statuses(db_session, tmp_path):
    company = _company(db_session)

    eligible_path = tmp_path / "eligible.pdf"
    _build_report_pdf(eligible_path, page_count=2)
    eligible = _report(
        db_session, company, eligible_path, sha256="1" * 64, page_count=2,
        metadata_status=MetadataStatus.VALIDATED,
    )

    rejected_path = tmp_path / "rejected.pdf"
    _build_report_pdf(rejected_path, page_count=2)
    _report(
        db_session, company, rejected_path, sha256="2" * 64, page_count=0,
        metadata_status=MetadataStatus.REJECTED,
    )

    discovered_path = tmp_path / "discovered.pdf"
    _build_report_pdf(discovered_path, page_count=2)
    _report(
        db_session, company, discovered_path, sha256="3" * 64, page_count=None,
        metadata_status=MetadataStatus.DISCOVERED,
    )

    outcome = extraction.extract_eligible_reports(db_session)

    processed_paths = set(outcome.completed) | set(outcome.completed_with_warnings)
    assert eligible.local_path in processed_paths
    assert rejected_path.as_posix() not in processed_paths
    assert discovered_path.as_posix() not in processed_paths


def test_extract_eligible_reports_continues_after_individual_failure(db_session, tmp_path):
    company = _company(db_session)

    good_path = tmp_path / "good.pdf"
    _build_report_pdf(good_path, page_count=2)
    _report(db_session, company, good_path, sha256="1" * 64, page_count=2)

    corrupt_path = tmp_path / "corrupt.pdf"
    _build_corrupt_pdf(corrupt_path)
    _report(
        db_session, company, corrupt_path, sha256="2" * 64, page_count=0,
        metadata_status=MetadataStatus.NEEDS_REVIEW,
    )

    outcome = extraction.extract_eligible_reports(db_session)

    assert len(outcome.failed) == 1
    assert len(outcome.completed) + len(outcome.completed_with_warnings) == 1


def test_extract_eligible_reports_respects_limit(db_session, tmp_path):
    company = _company(db_session)
    for i in range(3):
        path = tmp_path / f"report_{i}.pdf"
        _build_report_pdf(path, page_count=2)
        _report(db_session, company, path, sha256=str(i) * 64, page_count=2)

    outcome = extraction.extract_eligible_reports(db_session, limit=2)

    total_processed = (
        len(outcome.completed) + len(outcome.completed_with_warnings) + len(outcome.failed)
    )
    assert total_processed == 2
