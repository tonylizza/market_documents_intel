import fitz
from sqlalchemy import select

from market_documents.models.company import Company
from market_documents.models.enums import CanonicalExtractionStatus, MetadataStatus
from market_documents.models.pdf_source import CanonicalBlock, CanonicalPage
from market_documents.models.report import Report
from market_documents.services import canonical_extraction

GOOD_PARAGRAPH = (
    "The group delivered a resilient operating performance during the "
    "period under review, with revenue growth recorded across all "
    "reporting segments and continued margin discipline maintained. "
) * 2


def _build_report_pdf(path, page_count: int = 3) -> None:
    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page(width=400, height=600)
        page.insert_textbox(fitz.Rect(50, 50, 350, 550), GOOD_PARAGRAPH, fontsize=10)
    doc.save(str(path))
    doc.close()


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
        page_count=3,
        metadata_status=MetadataStatus.VALIDATED,
    )
    defaults.update(overrides)
    report = Report(**defaults)
    session.add(report)
    session.flush()
    return report


def test_run_canonical_extraction_completes_and_persists_hierarchy(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=3)
    report = _report(db_session, company, pdf_path)

    outcome = canonical_extraction.run_canonical_extraction(db_session, report)

    assert outcome.skipped is False
    run = outcome.run
    assert run.status == CanonicalExtractionStatus.COMPLETED
    assert run.processed_page_count == 3
    assert run.expected_page_count == 3

    pages = db_session.scalars(select(CanonicalPage).where(CanonicalPage.canonical_run_id == run.id)).all()
    assert len(pages) == 3

    blocks = db_session.scalars(
        select(CanonicalBlock).where(CanonicalBlock.page_id.in_([p.id for p in pages]))
    ).all()
    assert len(blocks) > 0

    # Reconstruct one block's text purely from its persisted spans.
    block = next(b for b in blocks if b.raw_text.strip())
    reconstructed = "\n".join(
        "".join(span.text for span in sorted(line.spans, key=lambda s: s.span_order))
        for line in sorted(block.lines, key=lambda l: l.line_order)
    )
    assert reconstructed.strip("\n") == block.raw_text


def test_run_canonical_extraction_is_idempotent_without_force(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=2)
    report = _report(db_session, company, pdf_path)

    first = canonical_extraction.run_canonical_extraction(db_session, report)
    second = canonical_extraction.run_canonical_extraction(db_session, report)

    assert second.skipped is True
    assert second.run.id == first.run.id


def test_run_canonical_extraction_force_creates_new_run(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=2)
    report = _report(db_session, company, pdf_path)

    first = canonical_extraction.run_canonical_extraction(db_session, report)
    second = canonical_extraction.run_canonical_extraction(db_session, report, force=True)

    assert second.skipped is False
    assert second.run.id != first.run.id


def test_get_current_canonical_run_returns_latest_completed(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=2)
    report = _report(db_session, company, pdf_path)

    outcome = canonical_extraction.run_canonical_extraction(db_session, report)

    current = canonical_extraction.get_current_canonical_run(db_session, report.id)
    assert current is not None
    assert current.id == outcome.run.id


def test_run_canonical_extraction_never_touches_legacy_tables(db_session, tmp_path):
    """7C.1a must not read or write the legacy Page/TextBlock/ExtractionRun
    tables at all -- it is a fully parallel track."""
    from market_documents.models.extraction import ExtractionRun, Page, TextBlock

    company = _company(db_session)
    pdf_path = tmp_path / "good.pdf"
    _build_report_pdf(pdf_path, page_count=2)
    report = _report(db_session, company, pdf_path)

    canonical_extraction.run_canonical_extraction(db_session, report)

    assert db_session.scalars(select(ExtractionRun).where(ExtractionRun.report_id == report.id)).all() == []
    assert db_session.scalars(select(Page).where(Page.report_id == report.id)).all() == []
    assert db_session.scalars(select(TextBlock).where(TextBlock.report_id == report.id)).all() == []
