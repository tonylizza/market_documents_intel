"""Source adapter: lets 7C.1 (`schedule_localization.py`,
`semantic_unit_extraction.py`) consume the canonical PDF source
representation (Track 7C.1a) instead of the legacy `Page`/`TextBlock`
tables, without changing either service's higher-level schedule/unit
models or pure algorithms (`localize_schedule`, `extract_unit`).

`SourcePage`/`SourceBlock`/`SourceLine`/`SourceSpan` are plain, ORM-free
dataclasses -- loaded once from the database, then never touch the
`Session` again. Block classification is intentionally *not* reimplemented
here: `classify_source_pages` reuses `block_classification.classify_block`
and `header_footer_detection.detect_header_footer_blocks` verbatim, by
reshaping canonical blocks into the same `pdf_extraction.ExtractedPage`/
`ExtractedBlock` shape the legacy pipeline already classifies. This is
deliberate -- see docs/7c1a-canonical-source-representation.md Section 4:
7C.1a's job is to fix the *source* representation, not to invent a second,
divergent classification heuristic.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import BlockType
from market_documents.models.pdf_source import CanonicalBlock, CanonicalLine, CanonicalPage, CanonicalSpan
from market_documents.services import block_classification, header_footer_detection
from market_documents.services.extraction_config import EXTRACTION_CONFIG
from market_documents.services.pdf_extraction import ExtractedBlock, ExtractedPage

# --------------------------------------------------------------------------
# Pure source objects
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSpan:
    id: uuid.UUID
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


@dataclass(frozen=True)
class SourceLine:
    id: uuid.UUID
    line_order: int
    x0: float
    y0: float
    x1: float
    y1: float
    spans: tuple[SourceSpan, ...]


@dataclass(frozen=True)
class SourceBlock:
    id: uuid.UUID
    block_order: int
    native_type: int
    x0: float
    y0: float
    x1: float
    y1: float
    raw_text: str
    lines: tuple[SourceLine, ...]


@dataclass(frozen=True)
class SourcePage:
    id: uuid.UUID
    page_number: int
    width: float
    height: float
    blocks: tuple[SourceBlock, ...]


def load_source_pages(session: Session, canonical_run_id: uuid.UUID) -> list[SourcePage]:
    """Load one canonical extraction run's full page/block/line/span
    hierarchy into ORM-free dataclasses, in native page/block/line/span
    order throughout."""
    pages = session.scalars(
        select(CanonicalPage)
        .where(CanonicalPage.canonical_run_id == canonical_run_id)
        .order_by(CanonicalPage.page_number)
    ).all()

    source_pages: list[SourcePage] = []
    for page in pages:
        blocks = session.scalars(
            select(CanonicalBlock).where(CanonicalBlock.page_id == page.id).order_by(CanonicalBlock.block_order)
        ).all()

        source_blocks: list[SourceBlock] = []
        for block in blocks:
            lines = session.scalars(
                select(CanonicalLine).where(CanonicalLine.block_id == block.id).order_by(CanonicalLine.line_order)
            ).all()

            source_lines: list[SourceLine] = []
            for line in lines:
                spans = session.scalars(
                    select(CanonicalSpan).where(CanonicalSpan.line_id == line.id).order_by(CanonicalSpan.span_order)
                ).all()
                source_spans = tuple(
                    SourceSpan(
                        id=s.id, span_order=s.span_order, text=s.text, x0=s.x0, y0=s.y0, x1=s.x1, y1=s.y1,
                        font_name=s.font_name, font_size=s.font_size, font_flags=s.font_flags,
                        is_bold=s.is_bold, color=s.color,
                    )
                    for s in spans
                )
                source_lines.append(
                    SourceLine(
                        id=line.id, line_order=line.line_order, x0=line.x0, y0=line.y0, x1=line.x1, y1=line.y1,
                        spans=source_spans,
                    )
                )

            source_blocks.append(
                SourceBlock(
                    id=block.id, block_order=block.block_order, native_type=block.native_type,
                    x0=block.x0, y0=block.y0, x1=block.x1, y1=block.y1, raw_text=block.raw_text,
                    lines=tuple(source_lines),
                )
            )

        source_pages.append(
            SourcePage(
                id=page.id, page_number=page.page_number, width=page.width, height=page.height,
                blocks=tuple(source_blocks),
            )
        )

    return source_pages


# --------------------------------------------------------------------------
# Classification: reuse the legacy block classifier against canonical input
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ClassifiedBlock:
    """A TextBlock-equivalent view of one canonical block, classified with
    the same rules `services.extraction._run_extraction` applies to legacy
    TextBlock rows -- but computed from the source-faithful canonical
    representation instead of the lossy persisted TextBlock rows.

    `font_size`/`is_bold` are the same per-block averages already computed
    for classification (`_block_font_stats`); `block_width_ratio` (Track
    7C.1b) is the block's width as a fraction of its page's width -- all
    three are carried through so `build_heading_blocks` can pass them to
    `schedule_localization.HeadingBlock` for structural assessment.
    """

    id: uuid.UUID
    page_number: int
    reading_order: int
    block_type: BlockType
    text: str
    excluded_from_narrative: bool
    font_size: float | None = None
    is_bold: bool | None = None
    block_width_ratio: float | None = None


def _block_font_stats(block: SourceBlock) -> tuple[float | None, bool | None]:
    sizes = [span.font_size for line in block.lines for span in line.spans if span.font_size is not None]
    bold_flags = [bool(span.is_bold) for line in block.lines for span in line.spans if span.is_bold is not None]
    font_size = round(sum(sizes) / len(sizes), 2) if sizes else None
    is_bold = (sum(bold_flags) > len(bold_flags) / 2) if bold_flags else None
    return font_size, is_bold


def _to_extracted_page(page: SourcePage) -> ExtractedPage:
    blocks: list[ExtractedBlock] = []
    for block in page.blocks:
        if block.native_type != 0:
            continue  # image block -- no text to classify
        text = block.raw_text.strip("\n")
        if not text.strip():
            continue
        font_size, is_bold = _block_font_stats(block)
        blocks.append(
            ExtractedBlock(
                block_index=block.block_order, text=text,
                x0=block.x0, y0=block.y0, x1=block.x1, y1=block.y1,
                font_size=font_size, is_bold=is_bold,
            )
        )
    return ExtractedPage(
        page_number=page.page_number, page_width=page.width, page_height=page.height,
        raw_text="\n\n".join(b.text for b in blocks), image_count=0, blocks=blocks,
    )


def classify_source_pages(pages: list[SourcePage]) -> list[ClassifiedBlock]:
    """Classify every text block across a canonical run's pages, reusing
    `block_classification.classify_block` and
    `header_footer_detection.detect_header_footer_blocks` unchanged. Returns
    one `ClassifiedBlock` per kept text block, in (page_number,
    reading_order) order -- the same shape `schedule_localization.py` and
    `semantic_unit_extraction.py` already consume via `HeadingBlock`/
    `UnitBlock`, just sourced from canonical spans instead of TextBlock.
    """
    extracted_pages = [_to_extracted_page(p) for p in pages]
    # Map (page_number, block_index) -> SourceBlock, for id lookup below.
    source_block_by_location = {
        (p.page_number, b.block_order): b for p in pages for b in p.blocks
    }

    header_footer_flags = header_footer_detection.detect_header_footer_blocks(extracted_pages, EXTRACTION_CONFIG)

    classified: list[ClassifiedBlock] = []
    for extracted_page in extracted_pages:
        font_sizes = [b.font_size for b in extracted_page.blocks if b.font_size is not None]
        page_median_font_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else None

        first_pass = []
        for reading_order, extracted_block in enumerate(extracted_page.blocks):
            hf_flags = header_footer_flags.get((extracted_page.page_number, extracted_block.block_index))
            is_header = bool(hf_flags and hf_flags.is_repeated_header)
            is_footer = bool(hf_flags and hf_flags.is_repeated_footer)

            block_type, excluded, _reason = block_classification.classify_block(
                extracted_block.text,
                is_repeated_header=is_header,
                is_repeated_footer=is_footer,
                font_size=extracted_block.font_size,
                is_bold=extracted_block.is_bold,
                page_median_font_size=page_median_font_size,
                config=EXTRACTION_CONFIG,
                bbox_height=extracted_block.y1 - extracted_block.y0,
            )
            first_pass.append((reading_order, extracted_block, block_type, excluded))

        table_header_fragment_indices = block_classification.find_table_header_fragment_indices(
            [
                block_classification.PageBlockGeometry(
                    block_type=entry[2], x0=entry[1].x0, y0=entry[1].y0, x1=entry[1].x1, y1=entry[1].y1
                )
                for entry in first_pass
            ],
            EXTRACTION_CONFIG,
        )

        for idx, (reading_order, extracted_block, block_type, excluded) in enumerate(first_pass):
            if idx in table_header_fragment_indices:
                block_type = BlockType.TABLE_HEADER_FRAGMENT
                excluded = True

            source_block = source_block_by_location[(extracted_page.page_number, extracted_block.block_index)]
            block_width = extracted_block.x1 - extracted_block.x0
            block_width_ratio = (
                block_width / extracted_page.page_width if extracted_page.page_width else None
            )
            classified.append(
                ClassifiedBlock(
                    id=source_block.id,
                    page_number=extracted_page.page_number,
                    reading_order=reading_order,
                    block_type=block_type,
                    text=extracted_block.text,
                    excluded_from_narrative=excluded,
                    font_size=extracted_block.font_size,
                    is_bold=extracted_block.is_bold,
                    block_width_ratio=block_width_ratio,
                )
            )

    return classified


# --------------------------------------------------------------------------
# 7C.1 adapters
# --------------------------------------------------------------------------


def build_heading_blocks(classified: list[ClassifiedBlock]) -> list:
    """`HeadingBlock` list for `schedule_localization.localize_schedule`,
    sourced from canonical classification instead of a TextBlock query."""
    from market_documents.services.schedule_localization import HeadingBlock

    return [
        HeadingBlock(
            id=b.id, page_number=b.page_number, reading_order=b.reading_order, text=b.text,
            font_size=b.font_size, is_bold=b.is_bold, block_width_ratio=b.block_width_ratio,
        )
        for b in classified
        if b.block_type == BlockType.HEADING_CANDIDATE and not b.excluded_from_narrative
    ]


def build_unit_blocks(classified: list[ClassifiedBlock], *, start_page: int, end_page: int) -> list:
    """`UnitBlock` list for `semantic_unit_extraction.extract_unit`,
    restricted to one schedule instance's page range, sourced from
    canonical classification instead of a TextBlock query."""
    from market_documents.services.semantic_unit_extraction import UnitBlock

    return [
        UnitBlock(id=b.id, page_number=b.page_number, reading_order=b.reading_order, block_type=b.block_type, text=b.text)
        for b in classified
        if start_page <= b.page_number <= end_page and not b.excluded_from_narrative
    ]
