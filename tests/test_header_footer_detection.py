from market_documents.services.extraction_config import ExtractionConfig
from market_documents.services.header_footer_detection import (
    detect_header_footer_blocks,
    normalize_candidate,
)
from market_documents.services.pdf_extraction import ExtractedBlock, ExtractedPage

CONFIG = ExtractionConfig()
PAGE_HEIGHT = 800.0


def _page(page_number: int, blocks: list[ExtractedBlock]) -> ExtractedPage:
    return ExtractedPage(
        page_number=page_number,
        page_width=600.0,
        page_height=PAGE_HEIGHT,
        raw_text="\n\n".join(b.text for b in blocks),
        image_count=0,
        blocks=blocks,
    )


def _top_block(text: str, index: int = 0) -> ExtractedBlock:
    return ExtractedBlock(block_index=index, text=text, x0=0, y0=10, x1=100, y1=20, font_size=8, is_bold=None)


def _bottom_block(text: str, index: int = 0) -> ExtractedBlock:
    return ExtractedBlock(
        block_index=index, text=text, x0=0, y0=780, x1=100, y1=790, font_size=8, is_bold=None
    )


def _mid_block(text: str, index: int = 0) -> ExtractedBlock:
    return ExtractedBlock(
        block_index=index, text=text, x0=0, y0=400, x1=300, y1=420, font_size=10, is_bold=None
    )


def test_normalize_candidate_collapses_digit_runs():
    assert normalize_candidate("Page 3 of 120") == normalize_candidate("Page 4 of 120")


def test_detects_repeated_footer_across_most_pages():
    pages = [
        _page(n, [_bottom_block(f"Company X Annual Report {n} of 8"), _mid_block("Unrelated body text")])
        for n in range(1, 9)
    ]

    flags = detect_header_footer_blocks(pages, CONFIG)

    for n in range(1, 9):
        assert flags[(n, 0)].is_repeated_footer is True
        assert (n, 1) not in flags


def test_detects_repeated_header_across_most_pages():
    pages = [
        _page(n, [_top_block("CONFIDENTIAL DRAFT"), _mid_block("Unrelated body text")])
        for n in range(1, 9)
    ]

    flags = detect_header_footer_blocks(pages, CONFIG)

    for n in range(1, 9):
        assert flags[(n, 0)].is_repeated_header is True


def test_does_not_flag_one_off_heading_in_top_region():
    """A heading that happens to appear near the top of a single page must
    not be mistaken for a repeated header -- it never recurs.
    """
    pages = [_page(n, [_mid_block("Unrelated body text")]) for n in range(1, 9)]
    pages[0].blocks.append(_top_block("Chairman's Statement"))

    flags = detect_header_footer_blocks(pages, CONFIG)

    assert (1, 1) not in flags


def test_does_not_flag_below_repetition_threshold():
    """Text that recurs on only a couple of pages, below the configured
    repetition threshold, is not furniture.
    """
    pages = [_page(n, [_mid_block("Unrelated body text")]) for n in range(1, 9)]
    pages[0].blocks.append(_top_block("Introduction"))
    pages[1].blocks.append(_top_block("Introduction"))

    flags = detect_header_footer_blocks(pages, CONFIG)

    assert not any(flags.get((n, 1)) for n in (1, 2))


def test_skips_detection_entirely_for_short_reports():
    """Reports shorter than the configured minimum page count never run
    header/footer detection, avoiding false positives on a short report's
    title page.
    """
    pages = [_page(n, [_top_block("Repeated Title")]) for n in range(1, 3)]
    assert len(pages) < CONFIG.header_footer_min_page_count

    flags = detect_header_footer_blocks(pages, CONFIG)

    assert flags == {}


def test_mid_page_block_never_flagged_as_header_or_footer():
    pages = [
        _page(n, [_mid_block("Repeated body sentence that happens to recur")])
        for n in range(1, 9)
    ]

    flags = detect_header_footer_blocks(pages, CONFIG)

    assert flags == {}
