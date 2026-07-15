import csv

import fitz

from market_documents.models.company import Company
from market_documents.models.enums import MetadataStatus
from market_documents.models.report import Report
from market_documents.services import extraction
from market_documents.services.corpus_audit import build_corpus_audit_rows, write_corpus_audit_csv

GOOD_PARAGRAPH = (
    "The group delivered a resilient operating performance during the "
    "period under review, with revenue growth recorded across all "
    "reporting segments and continued margin discipline. "
) * 3


def _build_report_pdf(path, page_count: int = 3) -> None:
    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page(width=400, height=600)
        page.insert_textbox(fitz.Rect(50, 50, 350, 550), GOOD_PARAGRAPH, fontsize=10)
    doc.save(str(path))
    doc.close()


def test_corpus_audit_works_with_no_extractions_at_all(db_session, tmp_path):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    pdf_path = tmp_path / "never_extracted.pdf"
    _build_report_pdf(pdf_path)
    report = Report(
        company_id=company.id,
        local_path=str(pdf_path),
        filename=pdf_path.name,
        sha256="a" * 64,
        directory_year=2024,
        page_count=3,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()

    rows = build_corpus_audit_rows(db_session)

    assert len(rows) == 1
    assert rows[0].ticker == "TST"
    assert rows[0].extraction_status is None
    assert rows[0].extraction_quality is None
    assert rows[0].processed_page_count is None


def test_corpus_audit_includes_extraction_diagnostics_after_extraction(db_session, tmp_path):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    pdf_path = tmp_path / "extracted.pdf"
    _build_report_pdf(pdf_path)
    report = Report(
        company_id=company.id,
        local_path=str(pdf_path),
        filename=pdf_path.name,
        sha256="b" * 64,
        directory_year=2024,
        page_count=3,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()

    extraction.extract_report(db_session, report)

    rows = build_corpus_audit_rows(db_session)

    assert len(rows) == 1
    row = rows[0]
    assert row.extraction_status is not None
    assert row.extraction_quality is not None
    assert row.processed_page_count == 3
    assert row.usable_page_percentage is not None


def test_corpus_audit_handles_mixed_success_and_failure(db_session, tmp_path):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    good_path = tmp_path / "good.pdf"
    _build_report_pdf(good_path)
    good_report = Report(
        company_id=company.id,
        local_path=str(good_path),
        filename=good_path.name,
        sha256="c" * 64,
        directory_year=2024,
        page_count=3,
        metadata_status=MetadataStatus.VALIDATED,
    )

    corrupt_path = tmp_path / "corrupt.pdf"
    corrupt_path.write_bytes(b"not a real pdf")
    corrupt_report = Report(
        company_id=company.id,
        local_path=str(corrupt_path),
        filename=corrupt_path.name,
        sha256="d" * 64,
        directory_year=2024,
        page_count=0,
        metadata_status=MetadataStatus.NEEDS_REVIEW,
    )
    db_session.add_all([good_report, corrupt_report])
    db_session.flush()

    extraction.extract_report(db_session, good_report)
    extraction.extract_report(db_session, corrupt_report)

    rows = build_corpus_audit_rows(db_session)
    rows_by_filename = {r.filename: r for r in rows}

    assert rows_by_filename["good.pdf"].extraction_status is not None
    # The corrupt report's only run failed, so it has no *current successful*
    # extraction -- diagnostics stay blank, exactly like an unextracted report.
    assert rows_by_filename["corrupt.pdf"].extraction_status is None


def test_write_corpus_audit_csv_round_trips(db_session, tmp_path):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    pdf_path = tmp_path / "extracted.pdf"
    _build_report_pdf(pdf_path)
    report = Report(
        company_id=company.id,
        local_path=str(pdf_path),
        filename=pdf_path.name,
        sha256="e" * 64,
        directory_year=2024,
        page_count=3,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()
    extraction.extract_report(db_session, report)

    rows = build_corpus_audit_rows(db_session)
    csv_path = tmp_path / "audit.csv"
    write_corpus_audit_csv(rows, csv_path)

    with csv_path.open() as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)

    assert len(csv_rows) == 1
    assert csv_rows[0]["ticker"] == "TST"
    assert csv_rows[0]["filename"] == "extracted.pdf"
