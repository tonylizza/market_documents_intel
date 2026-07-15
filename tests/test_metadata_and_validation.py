from datetime import date
from pathlib import Path

from pypdf import PdfWriter

from market_documents.models.company import Company
from market_documents.models.enums import MetadataSource, MetadataStatus
from market_documents.models.report import Report
from market_documents.services.metadata_inspection import (
    inspect_discovered_reports,
    inspect_report,
)
from market_documents.services.validation import validate_report, validate_reports


def _write_blank_pdf(path: Path, pages: int = 1) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as f:
        writer.write(f)


def _report(company: Company, path: Path, **overrides) -> Report:
    defaults = dict(
        company_id=company.id,
        local_path=str(path),
        filename=path.name,
        sha256=overrides.pop("sha256", "e" * 64),
        directory_year=2024,
        metadata_status=MetadataStatus.DISCOVERED,
        metadata_source=MetadataSource.DIRECTORY,
    )
    defaults.update(overrides)
    return Report(**defaults)


def test_inspect_report_sets_page_count_and_advances_status(tmp_path):
    pdf_path = tmp_path / "annual_report.pdf"
    _write_blank_pdf(pdf_path, pages=3)
    report = Report(
        company_id=None,
        local_path=str(pdf_path),
        filename=pdf_path.name,
        sha256="f" * 64,
        directory_year=2024,
        metadata_status=MetadataStatus.DISCOVERED,
        metadata_source=MetadataSource.DIRECTORY,
    )

    inspect_report(report)

    assert report.page_count == 3
    assert report.metadata_status == MetadataStatus.INSPECTED


def test_inspect_discovered_reports_handles_corrupt_pdf_without_crashing(db_session, tmp_path):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    corrupt_path = tmp_path / "corrupt.pdf"
    corrupt_path.write_bytes(b"not a real pdf")
    report = _report(company, corrupt_path)
    db_session.add(report)
    db_session.flush()

    outcome = inspect_discovered_reports(db_session)

    assert outcome.inspected == []
    assert len(outcome.failed) == 1
    assert report.metadata_status == MetadataStatus.DISCOVERED  # never advanced on failure


def test_validate_report_rejects_unreadable_reports():
    report = Report(page_count=None, period_end=None)
    assert validate_report(report) == MetadataStatus.REJECTED


def test_validate_report_marks_needs_review_when_period_end_unknown():
    report = Report(page_count=120, period_end=None)
    assert validate_report(report) == MetadataStatus.NEEDS_REVIEW


def test_validate_report_marks_validated_when_period_end_known():
    report = Report(page_count=120, period_end=date(2024, 12, 31))
    assert validate_report(report) == MetadataStatus.VALIDATED


def test_validate_reports_skips_discovered_and_updates_others(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    discovered = _report(
        company, Path("data/raw/TST/2024/a.pdf"), sha256="1" * 64, metadata_status=MetadataStatus.DISCOVERED
    )
    inspected_ready = _report(
        company,
        Path("data/raw/TST/2024/b.pdf"),
        sha256="2" * 64,
        metadata_status=MetadataStatus.INSPECTED,
        page_count=100,
        period_end=date(2024, 12, 31),
    )
    inspected_provisional = _report(
        company,
        Path("data/raw/TST/2024/c.pdf"),
        sha256="3" * 64,
        metadata_status=MetadataStatus.INSPECTED,
        page_count=100,
    )
    db_session.add_all([discovered, inspected_ready, inspected_provisional])
    db_session.flush()

    outcome = validate_reports(db_session)

    assert discovered.metadata_status == MetadataStatus.DISCOVERED
    assert outcome.validated == [inspected_ready.local_path]
    assert outcome.needs_review == [inspected_provisional.local_path]
