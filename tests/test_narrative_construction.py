from market_documents.models.company import Company
from market_documents.models.enums import BlockType, ExtractionQuality, ExtractionStatus, MetadataStatus
from market_documents.models.extraction import ExtractionRun, Page, TextBlock
from market_documents.models.report import Report
from market_documents.services.narrative_construction import (
    build_narrative_document,
    build_narrative_text,
    compute_content_hash,
)


def _setup_run(session) -> ExtractionRun:
    company = Company(ticker="TST", company_name="Test Co")
    session.add(company)
    session.flush()

    report = Report(
        company_id=company.id,
        local_path="data/raw/TST/2024/annual_report.pdf",
        filename="annual_report.pdf",
        sha256="a" * 64,
        directory_year=2024,
        metadata_status=MetadataStatus.VALIDATED,
    )
    session.add(report)
    session.flush()

    run = ExtractionRun(
        report_id=report.id,
        extractor_name="pymupdf",
        extractor_version="1.0.0",
        configuration_hash="hash",
        status=ExtractionStatus.RUNNING,
    )
    session.add(run)
    session.flush()
    return run


def _add_page(session, run, page_number) -> Page:
    page = Page(
        extraction_run_id=run.id,
        report_id=run.report_id,
        page_number=page_number,
        raw_text="",
        character_count=0,
        word_count=0,
        block_count=0,
        native_text_available=True,
        suspected_image_only=False,
        extraction_quality=ExtractionQuality.GOOD,
    )
    session.add(page)
    session.flush()
    return page


def _add_block(
    session, run, page, reading_order, text, *, block_type=BlockType.PARAGRAPH, excluded=False
) -> TextBlock:
    block = TextBlock(
        extraction_run_id=run.id,
        page_id=page.id,
        report_id=run.report_id,
        block_index=reading_order,
        reading_order=reading_order,
        raw_text=text,
        cleaned_text=text,
        block_type=block_type,
        excluded_from_narrative=excluded,
    )
    session.add(block)
    return block


def test_narrative_text_follows_page_and_reading_order(db_session):
    run = _setup_run(db_session)
    page1 = _add_page(db_session, run, 1)
    page2 = _add_page(db_session, run, 2)

    _add_block(db_session, run, page2, 0, "Second page, first block")
    _add_block(db_session, run, page1, 1, "First page, second block")
    _add_block(db_session, run, page1, 0, "First page, first block")
    db_session.flush()

    text = build_narrative_text(db_session, run.id)

    assert text.index("First page, first block") < text.index("First page, second block")
    assert text.index("First page, second block") < text.index("Second page, first block")


def test_narrative_text_excludes_flagged_blocks(db_session):
    run = _setup_run(db_session)
    page = _add_page(db_session, run, 1)

    _add_block(db_session, run, page, 0, "Repeated Footer Text", block_type=BlockType.FOOTER, excluded=True)
    _add_block(db_session, run, page, 1, "Meaningful narrative paragraph.")
    _add_block(db_session, run, page, 2, "45.2 12.8", block_type=BlockType.NUMERIC_FRAGMENT, excluded=True)
    db_session.flush()

    text = build_narrative_text(db_session, run.id)

    assert "Meaningful narrative paragraph." in text
    assert "Repeated Footer Text" not in text
    assert "45.2 12.8" not in text


def test_narrative_document_word_count_and_content_hash(db_session):
    run = _setup_run(db_session)
    page = _add_page(db_session, run, 1)
    _add_block(db_session, run, page, 0, "Four distinct words here")
    db_session.flush()

    document = build_narrative_document(db_session, run)
    db_session.flush()

    assert document.word_count == 4
    assert document.content_hash == compute_content_hash(document.cleaned_text)


def test_narrative_text_is_regenerable_and_deterministic(db_session):
    run = _setup_run(db_session)
    page = _add_page(db_session, run, 1)
    _add_block(db_session, run, page, 0, "Stable narrative content")
    db_session.flush()

    first = build_narrative_text(db_session, run.id)
    second = build_narrative_text(db_session, run.id)

    assert first == second
    assert compute_content_hash(first) == compute_content_hash(second)


def test_narrative_text_empty_when_all_blocks_excluded(db_session):
    run = _setup_run(db_session)
    page = _add_page(db_session, run, 1)
    _add_block(db_session, run, page, 0, "Page 1", block_type=BlockType.PAGE_NUMBER, excluded=True)
    db_session.flush()

    text = build_narrative_text(db_session, run.id)

    assert text == ""
