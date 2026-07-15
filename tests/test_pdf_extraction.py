from pathlib import Path

import fitz

from market_documents.services.pdf_extraction import extract_pages


def _build_pdf(path: Path, page_texts: list[list[tuple[str, int, str]]]) -> None:
    """page_texts: one list of (text, fontsize, fontname) per page."""
    doc = fitz.open()
    for entries in page_texts:
        page = doc.new_page(width=400, height=600)
        y = 50
        for text, fontsize, fontname in entries:
            page.insert_text((50, y), text, fontsize=fontsize, fontname=fontname)
            y += fontsize + 20
    doc.save(str(path))
    doc.close()


def test_extract_pages_reports_page_number_and_count(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(
        path,
        [
            [("Page one text", 10, "helv")],
            [("Page two text", 10, "helv")],
        ],
    )
    with fitz.open(str(path)) as doc:
        pages = extract_pages(doc)

    assert len(pages) == 2
    assert [p.page_number for p in pages] == [1, 2]


def test_extract_pages_captures_block_text_and_coordinates(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("Hello there", 12, "helv")]])

    with fitz.open(str(path)) as doc:
        pages = extract_pages(doc)

    blocks = pages[0].blocks
    assert len(blocks) == 1
    block = blocks[0]
    assert "Hello there" in block.text
    assert block.x0 >= 0
    assert block.y1 > block.y0
    assert block.font_size == 12


def test_extract_pages_detects_bold_font(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("Bold text", 14, "hebo")]])

    with fitz.open(str(path)) as doc:
        pages = extract_pages(doc)

    assert pages[0].blocks[0].is_bold is True


def test_extract_pages_preserves_reading_order_via_block_index(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(
        path,
        [
            [
                ("First block", 12, "helv"),
                ("Second block", 12, "helv"),
                ("Third block", 12, "helv"),
            ]
        ],
    )

    with fitz.open(str(path)) as doc:
        pages = extract_pages(doc)

    texts_in_order = [b.text for b in pages[0].blocks]
    assert texts_in_order == ["First block", "Second block", "Third block"]


def test_extract_pages_empty_page_has_no_blocks_and_low_word_count(tmp_path):
    doc = fitz.open()
    doc.new_page(width=400, height=600)  # blank page, no text at all
    path = tmp_path / "blank.pdf"
    doc.save(str(path))
    doc.close()

    with fitz.open(str(path)) as reopened:
        pages = extract_pages(reopened)

    assert pages[0].blocks == []
    assert pages[0].raw_text == ""
