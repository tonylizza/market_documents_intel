"""Native, page-aware PDF extraction via PyMuPDF.

Produces plain, DB-independent dataclasses so this step is testable
without a database and so the header/footer detection pass (which needs
to see every page of a report at once) has something cheap to operate on
before anything is persisted.
"""

from dataclasses import dataclass, field

import fitz

_BOLD_FLAG = 1 << 4  # PyMuPDF span flag bit for bold text
_TEXT_BLOCK_TYPE = 0  # PyMuPDF block "type": 0 = text, 1 = image


@dataclass
class ExtractedBlock:
    block_index: int
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    font_size: float | None
    is_bold: bool | None


@dataclass
class ExtractedPage:
    page_number: int  # 1-indexed
    page_width: float
    page_height: float
    raw_text: str
    image_count: int
    blocks: list[ExtractedBlock] = field(default_factory=list)


def _flatten_block_text(raw_block: dict) -> tuple[str, float | None, bool | None]:
    line_texts: list[str] = []
    sizes: list[float] = []
    bold_flags: list[bool] = []
    for line in raw_block.get("lines", []):
        span_texts = []
        for span in line.get("spans", []):
            span_texts.append(span.get("text", ""))
            size = span.get("size")
            if size is not None:
                sizes.append(size)
            bold_flags.append(bool(span.get("flags", 0) & _BOLD_FLAG))
        line_texts.append("".join(span_texts))

    text = "\n".join(line_texts)
    font_size = round(sum(sizes) / len(sizes), 2) if sizes else None
    is_bold = (sum(bold_flags) > len(bold_flags) / 2) if bold_flags else None
    return text, font_size, is_bold


def extract_page(page: "fitz.Page", page_number: int) -> ExtractedPage:
    page_dict = page.get_text("dict")
    blocks: list[ExtractedBlock] = []
    raw_text_parts: list[str] = []

    for block_index, raw_block in enumerate(page_dict.get("blocks", [])):
        if raw_block.get("type") != _TEXT_BLOCK_TYPE:
            continue

        text, font_size, is_bold = _flatten_block_text(raw_block)
        text = text.strip("\n")
        if not text.strip():
            continue

        x0, y0, x1, y1 = raw_block.get("bbox", (0.0, 0.0, 0.0, 0.0))
        blocks.append(
            ExtractedBlock(
                block_index=block_index,
                text=text,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                font_size=font_size,
                is_bold=is_bold,
            )
        )
        raw_text_parts.append(text)

    image_count = len(page.get_images(full=False))

    return ExtractedPage(
        page_number=page_number,
        page_width=page.rect.width,
        page_height=page.rect.height,
        raw_text="\n\n".join(raw_text_parts),
        image_count=image_count,
        blocks=blocks,
    )


def extract_pages(doc: "fitz.Document") -> list[ExtractedPage]:
    """Extract every page of an already-open document, in page order."""
    return [extract_page(doc[index], page_number=index + 1) for index in range(doc.page_count)]
