"""Deterministic, feature-based block classification.

This is a transparent rule set, not a trained layout model. Every block
receives a classification and is always persisted regardless of the
outcome; classification only additionally decides whether a block is
excluded from the narrative corpus (with a recorded reason), never
whether it is stored at all.

Rules are evaluated in priority order: repeated header/footer (a
run-wide, high-confidence signal) first, then isolated page numbers, then
decorative/URL fragments, then numeric-density-based table/fragment
detection, then list items, then heading-like short blocks, defaulting to
PARAGRAPH.
"""

import re

from market_documents.models.enums import BlockType
from market_documents.services.extraction_config import ExtractionConfig

_PAGE_NUMBER_DIGIT_RE = re.compile(r"(?:page\s+)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?", re.IGNORECASE)
_ROMAN_NUMERAL_RE = re.compile(r"m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^\s*([-•●▪*]|\d+[.)])\s+")
_URL_RE = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?]\s*$")


def _digit_ratio(text: str) -> float:
    return sum(ch.isdigit() for ch in text) / len(text) if text else 0.0


def _alpha_ratio(text: str) -> float:
    return sum(ch.isalpha() for ch in text) / len(text) if text else 0.0


def _looks_like_page_number(stripped: str) -> bool:
    if _PAGE_NUMBER_DIGIT_RE.fullmatch(stripped):
        return True
    if 1 <= len(stripped) <= 5 and _ROMAN_NUMERAL_RE.fullmatch(stripped):
        return True
    return False


def classify_block(
    text: str,
    *,
    is_repeated_header: bool,
    is_repeated_footer: bool,
    font_size: float | None,
    is_bold: bool | None,
    page_median_font_size: float | None,
    config: ExtractionConfig,
) -> tuple[BlockType, bool, str | None]:
    """Return (block_type, excluded_from_narrative, exclusion_reason)."""
    stripped = text.strip()
    word_count = len(stripped.split())

    if is_repeated_header:
        return BlockType.HEADER, True, "repeated header detected across report pages"
    if is_repeated_footer:
        return BlockType.FOOTER, True, "repeated footer detected across report pages"

    if not stripped:
        return BlockType.UNKNOWN, True, "empty block"

    if word_count <= 6 and _looks_like_page_number(stripped):
        return BlockType.PAGE_NUMBER, True, "isolated page number"

    if word_count <= config.decorative_max_words and (
        _URL_RE.match(stripped) or (_alpha_ratio(stripped) < 0.3 and _digit_ratio(stripped) < 0.3)
    ):
        return BlockType.DECORATIVE_OR_FRAGMENT, True, "decorative or navigation fragment"

    digit_ratio = _digit_ratio(stripped)
    numeric_token_count = sum(1 for token in stripped.split() if any(ch.isdigit() for ch in token))

    if digit_ratio >= config.table_like_min_digit_ratio and numeric_token_count >= config.table_like_min_numeric_tokens:
        return BlockType.TABLE_LIKE, True, "table-like numeric content"

    if digit_ratio >= config.numeric_fragment_min_digit_ratio and word_count <= config.numeric_fragment_max_words:
        return BlockType.NUMERIC_FRAGMENT, True, "standalone numeric fragment"

    if _LIST_ITEM_RE.match(stripped):
        return BlockType.LIST_ITEM, False, None

    is_heading_like_font = (
        font_size is not None and page_median_font_size is not None and font_size > page_median_font_size * 1.15
    )
    is_shouty = stripped.isupper()
    if word_count <= config.heading_max_words and not _SENTENCE_END_RE.search(stripped) and (
        is_heading_like_font or bool(is_bold) or is_shouty
    ):
        return BlockType.HEADING_CANDIDATE, False, None

    return BlockType.PARAGRAPH, False, None
