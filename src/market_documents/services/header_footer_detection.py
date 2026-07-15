"""Report-level detection of repeated page furniture (running headers/footers).

Blocks are never assumed to be furniture just because of their position.
A candidate is only marked as a repeated header or footer once its
normalized text recurs across a configurable fraction of the run's pages,
and detection is skipped entirely for reports too short to establish a
meaningful pattern -- both guard against misclassifying a one-off heading
or a short report's title.
"""

import re
from dataclasses import dataclass

from market_documents.services.extraction_config import ExtractionConfig
from market_documents.services.pdf_extraction import ExtractedPage

_DIGIT_RUN_RE = re.compile(r"\d+")
_WHITESPACE_RE = re.compile(r"\s+")

BlockLocation = tuple[int, int]  # (page_number, block_index)


@dataclass(frozen=True)
class HeaderFooterFlags:
    is_repeated_header: bool
    is_repeated_footer: bool


def normalize_candidate(text: str) -> str:
    """Normalize a block's text for repetition matching.

    Digit runs are collapsed to a single placeholder so that a running
    footer like "Page 3 of 120" still matches "Page 4 of 120" across pages.
    """
    text = text.strip().lower()
    text = _DIGIT_RUN_RE.sub("#", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text


def detect_header_footer_blocks(
    pages: list[ExtractedPage], config: ExtractionConfig
) -> dict[BlockLocation, HeaderFooterFlags]:
    """Return {(page_number, block_index): HeaderFooterFlags} for blocks
    that recur often enough near the top/bottom of pages to be furniture.
    """
    flags: dict[BlockLocation, HeaderFooterFlags] = {}
    if len(pages) < config.header_footer_min_page_count:
        return flags

    header_candidates: dict[str, list[BlockLocation]] = {}
    footer_candidates: dict[str, list[BlockLocation]] = {}

    for page in pages:
        if page.page_height <= 0:
            continue
        top_boundary = page.page_height * config.top_region_fraction
        bottom_boundary = page.page_height * (1 - config.bottom_region_fraction)

        for block in page.blocks:
            normalized = normalize_candidate(block.text)
            if not normalized:
                continue
            location = (page.page_number, block.block_index)
            if block.y1 <= top_boundary:
                header_candidates.setdefault(normalized, []).append(location)
            elif block.y0 >= bottom_boundary:
                footer_candidates.setdefault(normalized, []).append(location)

    total_pages = len(pages)
    min_recurrence = max(2, round(total_pages * config.header_footer_repetition_threshold))

    def _apply(candidates: dict[str, list[BlockLocation]], *, is_header: bool) -> None:
        for locations in candidates.values():
            distinct_pages = {page_number for page_number, _ in locations}
            if len(distinct_pages) < min_recurrence:
                continue
            for location in locations:
                flags[location] = HeaderFooterFlags(
                    is_repeated_header=is_header, is_repeated_footer=not is_header
                )

    _apply(header_candidates, is_header=True)
    _apply(footer_candidates, is_header=False)

    return flags
