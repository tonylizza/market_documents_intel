"""Canonical, source-faithful PDF extraction via PyMuPDF (Track 7C.1a).

Produces plain, DB-independent dataclasses -- mirrors `pdf_extraction.py`'s
own split between pure extraction and DB orchestration -- but captures the
full block/line/span hierarchy PyMuPDF's `get_text("dict")` already
provides, instead of flattening it into one text/font_size/is_bold value
per block the way `pdf_extraction.extract_page` does.

No sorting, cleaning, filtering, or classification happens here. Native
PyMuPDF block/line/span order is preserved exactly as emitted -- a global
y-sort was shown to corrupt multi-column layouts (see
docs/experiments/annual-report-extraction-representation-bakeoff.md) --
and nothing is discarded, including empty spans, image blocks, or apparent
page furniture. See docs/7c1a-canonical-source-representation.md for why
this layer exists alongside (never in place of) `pdf_extraction.py`.
"""

from dataclasses import dataclass, field

import fitz

_BOLD_FLAG = 1 << 4  # PyMuPDF span flag bit for bold text


@dataclass
class ExtractedSpan:
    span_order: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_name: str | None
    font_size: float | None
    font_flags: int | None
    is_bold: bool | None
    color: int | None


@dataclass
class ExtractedLine:
    line_order: int
    x0: float
    y0: float
    x1: float
    y1: float
    spans: list[ExtractedSpan] = field(default_factory=list)


@dataclass
class ExtractedCanonicalBlock:
    block_order: int
    native_type: int
    x0: float
    y0: float
    x1: float
    y1: float
    raw_text: str
    lines: list[ExtractedLine] = field(default_factory=list)


@dataclass
class ExtractedCanonicalPage:
    page_number: int  # 1-indexed
    width: float
    height: float
    blocks: list[ExtractedCanonicalBlock] = field(default_factory=list)


def _extract_span(span_order: int, raw_span: dict) -> ExtractedSpan:
    x0, y0, x1, y1 = raw_span.get("bbox", (0.0, 0.0, 0.0, 0.0))
    flags = raw_span.get("flags")
    return ExtractedSpan(
        span_order=span_order,
        text=raw_span.get("text", ""),
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        font_name=raw_span.get("font"),
        font_size=raw_span.get("size"),
        font_flags=flags,
        is_bold=bool(flags & _BOLD_FLAG) if flags is not None else None,
        color=raw_span.get("color"),
    )


def _extract_line(line_order: int, raw_line: dict) -> ExtractedLine:
    x0, y0, x1, y1 = raw_line.get("bbox", (0.0, 0.0, 0.0, 0.0))
    spans = [_extract_span(i, raw_span) for i, raw_span in enumerate(raw_line.get("spans", []))]
    return ExtractedLine(line_order=line_order, x0=x0, y0=y0, x1=x1, y1=y1, spans=spans)


def _block_raw_text(lines: list[ExtractedLine]) -> str:
    return "\n".join("".join(span.text for span in line.spans) for line in lines)


def _extract_block(block_order: int, raw_block: dict) -> ExtractedCanonicalBlock:
    x0, y0, x1, y1 = raw_block.get("bbox", (0.0, 0.0, 0.0, 0.0))
    native_type = raw_block.get("type", 0)
    lines = (
        [_extract_line(i, raw_line) for i, raw_line in enumerate(raw_block.get("lines", []))]
        if native_type == 0
        else []
    )
    return ExtractedCanonicalBlock(
        block_order=block_order,
        native_type=native_type,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        raw_text=_block_raw_text(lines),
        lines=lines,
    )


def extract_canonical_page(page: "fitz.Page", page_number: int) -> ExtractedCanonicalPage:
    page_dict = page.get_text("dict")
    blocks = [_extract_block(i, raw_block) for i, raw_block in enumerate(page_dict.get("blocks", []))]
    return ExtractedCanonicalPage(
        page_number=page_number,
        width=page.rect.width,
        height=page.rect.height,
        blocks=blocks,
    )


def extract_canonical_pages(doc: "fitz.Document") -> list[ExtractedCanonicalPage]:
    """Extract every page of an already-open document, in page order."""
    return [extract_canonical_page(doc[index], page_number=index + 1) for index in range(doc.page_count)]
