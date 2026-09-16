import fitz
from sqlalchemy import select

from market_documents.models.company import Company
from market_documents.models.enums import BlockType, MetadataStatus, NormalizedSchedule
from market_documents.models.report import Report
from market_documents.services import canonical_extraction, source_adapter
from market_documents.services.schedule_localization import HeadingBlock, localize_schedule
from market_documents.services.semantic_unit_config import BEL_GROSS_MARGIN
from market_documents.services.semantic_unit_extraction import UnitBlock, extract_unit


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
        sha256=overrides.pop("sha256", "b" * 64),
        directory_year=2024,
        page_count=2,
        metadata_status=MetadataStatus.VALIDATED,
    )
    defaults.update(overrides)
    report = Report(**defaults)
    session.add(report)
    session.flush()
    return report


def _build_schedule_pdf(path) -> None:
    """Page 1: a bold heading-like line ('Finance director's report')
    followed by ordinary paragraph text. Page 2: another heading-like line
    ('Corporate governance report') marking the next section."""
    doc = fitz.open()

    page1 = doc.new_page(width=400, height=600)
    page1.insert_text((50, 50), "Finance director's report", fontsize=16, fontname="hebo")
    page1.insert_textbox(
        fitz.Rect(50, 90, 350, 300),
        "Gross Margin The gross margin improved to 19,7% compared with 18,4% "
        "in the prior year. Continued cost discipline was maintained.",
        fontsize=10,
    )

    page2 = doc.new_page(width=400, height=600)
    page2.insert_text((50, 50), "Corporate governance report", fontsize=16, fontname="hebo")
    page2.insert_textbox(fitz.Rect(50, 90, 350, 300), "Governance content follows here.", fontsize=10)

    doc.save(str(path))
    doc.close()


def test_source_adapter_loads_pages_without_reading_legacy_tables(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "schedule.pdf"
    _build_schedule_pdf(pdf_path)
    report = _report(db_session, company, pdf_path, page_count=2)

    outcome = canonical_extraction.run_canonical_extraction(db_session, report)
    source_pages = source_adapter.load_source_pages(db_session, outcome.run.id)

    assert [p.page_number for p in source_pages] == [1, 2]
    assert all(isinstance(p.blocks, tuple) for p in source_pages)
    all_span_text = " ".join(
        span.text for p in source_pages for b in p.blocks for l in b.lines for span in l.spans
    )
    assert "Finance director" in all_span_text
    assert "Corporate governance" in all_span_text


def test_classify_source_pages_identifies_heading_candidates(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "schedule.pdf"
    _build_schedule_pdf(pdf_path)
    report = _report(db_session, company, pdf_path, page_count=2)

    outcome = canonical_extraction.run_canonical_extraction(db_session, report)
    source_pages = source_adapter.load_source_pages(db_session, outcome.run.id)
    classified = source_adapter.classify_source_pages(source_pages)

    headings = [c for c in classified if c.block_type == BlockType.HEADING_CANDIDATE]
    heading_texts = {h.text.strip() for h in headings}
    assert "Finance director's report" in heading_texts
    assert "Corporate governance report" in heading_texts


def test_schedule_localization_consumes_canonical_source_via_adapter(db_session, tmp_path):
    """Feeds `localize_schedule` (the unmodified pure 7C.1 algorithm) with
    HeadingBlocks built entirely from canonical source data -- no TextBlock
    involved anywhere in this test."""
    company = _company(db_session)
    pdf_path = tmp_path / "schedule.pdf"
    _build_schedule_pdf(pdf_path)
    report = _report(db_session, company, pdf_path, page_count=2)

    outcome = canonical_extraction.run_canonical_extraction(db_session, report)
    source_pages = source_adapter.load_source_pages(db_session, outcome.run.id)
    classified = source_adapter.classify_source_pages(source_pages)
    headings = source_adapter.build_heading_blocks(classified)

    assert all(isinstance(h, HeadingBlock) for h in headings)

    result = localize_schedule(headings, last_page_number=2, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE)
    assert result.primary is not None
    assert "Finance director" in result.primary.heading_text


def test_semantic_unit_extraction_consumes_canonical_source_via_adapter(db_session, tmp_path):
    company = _company(db_session)
    pdf_path = tmp_path / "schedule.pdf"
    _build_schedule_pdf(pdf_path)
    report = _report(db_session, company, pdf_path, page_count=2)

    outcome = canonical_extraction.run_canonical_extraction(db_session, report)
    source_pages = source_adapter.load_source_pages(db_session, outcome.run.id)
    classified = source_adapter.classify_source_pages(source_pages)
    unit_blocks = source_adapter.build_unit_blocks(classified, start_page=1, end_page=1)

    assert all(isinstance(b, UnitBlock) for b in unit_blocks)

    result = extract_unit(unit_blocks, BEL_GROSS_MARGIN)
    assert result is not None
    assert "gross margin" in result.source_text.lower()
