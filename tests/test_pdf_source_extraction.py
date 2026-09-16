from pathlib import Path

import fitz

from market_documents.services.pdf_source_extraction import extract_canonical_pages


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


def test_extract_canonical_pages_reports_page_number_and_geometry(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("Page one text", 10, "helv")], [("Page two text", 10, "helv")]])

    with fitz.open(str(path)) as doc:
        pages = extract_canonical_pages(doc)

    assert [p.page_number for p in pages] == [1, 2]
    assert pages[0].width > 0
    assert pages[0].height > 0


def test_extract_canonical_pages_preserves_native_block_order(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(
        path,
        [[("First block", 12, "helv"), ("Second block", 12, "helv"), ("Third block", 12, "helv")]],
    )

    with fitz.open(str(path)) as doc:
        pages = extract_canonical_pages(doc)

    blocks = [b for b in pages[0].blocks if b.native_type == 0]
    assert [b.block_order for b in blocks] == list(range(len(blocks)))
    assert [b.raw_text for b in blocks] == ["First block", "Second block", "Third block"]


def test_extract_canonical_pages_preserves_bbox(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("Hello there", 12, "helv")]])

    with fitz.open(str(path)) as doc:
        pages = extract_canonical_pages(doc)

    block = next(b for b in pages[0].blocks if b.native_type == 0)
    assert block.x0 >= 0
    assert block.y1 > block.y0
    assert block.x1 > block.x0


def test_extract_canonical_pages_preserves_line_and_span_hierarchy(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("Hello there", 12, "helv")]])

    with fitz.open(str(path)) as doc:
        pages = extract_canonical_pages(doc)

    block = next(b for b in pages[0].blocks if b.native_type == 0)
    assert len(block.lines) >= 1
    line = block.lines[0]
    assert len(line.spans) >= 1
    span = line.spans[0]
    assert "Hello" in span.text or "there" in span.text


def test_extract_canonical_pages_preserves_exact_span_text(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("Exact Span Text 123", 12, "helv")]])

    with fitz.open(str(path)) as doc:
        pages = extract_canonical_pages(doc)

    block = next(b for b in pages[0].blocks if b.native_type == 0)
    reconstructed = "".join(span.text for line in block.lines for span in line.spans)
    assert reconstructed == "Exact Span Text 123"


def test_extract_canonical_pages_preserves_font_size_and_bold_metadata(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("Bold text", 14, "hebo")]])

    with fitz.open(str(path)) as doc:
        pages = extract_canonical_pages(doc)

    block = next(b for b in pages[0].blocks if b.native_type == 0)
    span = block.lines[0].spans[0]
    assert span.font_size == 14
    assert span.is_bold is True
    assert span.font_name is not None


def test_extract_canonical_pages_does_not_globally_sort_blocks(tmp_path):
    """A block's position in `page.blocks` must reflect PyMuPDF's own raw
    emission order, not a y-coordinate sort -- a global y-sort was found to
    corrupt multi-column layouts (see the extraction-representation
    bakeoff doc). Inserting a block visually above an earlier one must not
    change its position in the block list."""
    path = tmp_path / "doc.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)
    page.insert_text((50, 400), "Lower block inserted first", fontsize=12, fontname="helv")
    page.insert_text((50, 50), "Upper block inserted second", fontsize=12, fontname="helv")
    doc.save(str(path))
    doc.close()

    with fitz.open(str(path)) as reopened:
        pages = extract_canonical_pages(reopened)

    blocks = [b for b in pages[0].blocks if b.native_type == 0]
    assert blocks[0].raw_text == "Lower block inserted first"
    assert blocks[1].raw_text == "Upper block inserted second"


def test_extract_canonical_pages_does_not_discard_short_or_empty_content(tmp_path):
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("X", 10, "helv"), ("Normal paragraph text here.", 10, "helv")]])

    with fitz.open(str(path)) as doc:
        pages = extract_canonical_pages(doc)

    blocks = [b for b in pages[0].blocks if b.native_type == 0]
    texts = [b.raw_text for b in blocks]
    assert "X" in texts


def test_extract_canonical_pages_no_loss_regression_against_raw_pymupdf_text(tmp_path):
    """Every word PyMuPDF's own plain-text layer reports for a page must be
    reconstructable from the canonical span text -- the exact property the
    legacy TextBlock layer was found to violate (BEL 2020's Gross Margin
    paragraph)."""
    path = tmp_path / "doc.pdf"
    _build_pdf(path, [[("The gross margin is dependent on many things.", 11, "helv")]])

    with fitz.open(str(path)) as doc:
        raw_text = doc[0].get_text("text")
        pages = extract_canonical_pages(doc)

    reconstructed = " ".join(
        span.text for block in pages[0].blocks for line in block.lines for span in line.spans
    )
    for word in raw_text.split():
        assert word in reconstructed
