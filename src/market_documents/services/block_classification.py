"""Deterministic, feature-based block classification.

This is a transparent rule set, not a trained layout model. Every block
receives a classification and is always persisted regardless of the
outcome; classification only additionally decides whether a block is
excluded from the narrative corpus (with a recorded reason), never
whether it is stored at all.

Rules are evaluated in priority order: repeated header/footer (a
run-wide, high-confidence signal) first, then the geometric
overlapping-text-artifact check (a structural signal independent of word
content, so it must run before any word-count-based rule could be
confused by a corrupted block's inflated word count), then isolated page
numbers, then decorative/URL fragments (including isolated single
alphabetic characters -- see below), then numeric-density-based
table/fragment detection (including the dense multi-line-per-cell table
variant), then list items, then heading-like short blocks, defaulting to
PARAGRAPH.

Isolated single alphabetic characters (e.g. a lone "O" or "E" block) are
excluded as decorative fragments before the heading-candidate check runs.
This must happen there: a single capitalized letter trivially satisfies
`is_shouty` (`stripped.isupper()` has no minimum length), so without this
rule it would become a spurious `HEADING_WITH_BODY` passage -- and because
passages with `heading_text` are exempt from the segmentation word-count
floor, it would survive as a near-empty passage rather than being dropped.
This is the signature of curved/rotated infographic text (e.g. a circular
wheel-diagram label): PyMuPDF cannot place such text on one horizontal
run, so each glyph becomes its own block. Valid roman-numeral single
letters ("I", "V", "X", ...) are unaffected -- the page-number check above
already claims those.
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


def _line_density(text: str, bbox_height: float | None) -> float | None:
    """Lines per point of bounding-box height, or None if height is unknown.

    A real, physically distinct line of text needs several points of
    vertical space; a block whose line count vastly exceeds what its own
    bounding box could hold is evidence of overlapping/duplicated text
    objects occupying nearly the same position, not of dense prose.
    """
    if not bbox_height or bbox_height <= 0:
        return None
    line_count = text.count("\n") + 1
    return line_count / bbox_height


def classify_block(
    text: str,
    *,
    is_repeated_header: bool,
    is_repeated_footer: bool,
    font_size: float | None,
    is_bold: bool | None,
    page_median_font_size: float | None,
    config: ExtractionConfig,
    bbox_height: float | None = None,
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

    line_density = _line_density(text, bbox_height)
    if line_density is not None and line_density > config.overlapping_text_line_density_threshold:
        return (
            BlockType.OVERLAPPING_TEXT_ARTIFACT,
            True,
            f"overlapping/duplicated text objects (line density {line_density:.2f} "
            f"exceeds {config.overlapping_text_line_density_threshold})",
        )

    if word_count <= 6 and _looks_like_page_number(stripped):
        return BlockType.PAGE_NUMBER, True, "isolated page number"

    if word_count <= config.decorative_max_words and (
        _URL_RE.match(stripped) or (_alpha_ratio(stripped) < 0.3 and _digit_ratio(stripped) < 0.3)
    ):
        return BlockType.DECORATIVE_OR_FRAGMENT, True, "decorative or navigation fragment"

    if word_count == 1 and len(stripped) == 1 and stripped.isalpha():
        return (
            BlockType.DECORATIVE_OR_FRAGMENT,
            True,
            "isolated single alphabetic character -- likely one glyph of curved/rotated "
            "infographic text (e.g. a circular wheel-diagram label), not a real word or heading",
        )

    digit_ratio = _digit_ratio(stripped)
    numeric_token_count = sum(1 for token in stripped.split() if any(ch.isdigit() for ch in token))

    if digit_ratio >= config.table_like_min_digit_ratio and numeric_token_count >= config.table_like_min_numeric_tokens:
        return BlockType.TABLE_LIKE, True, "table-like numeric content"

    # A table row whose text label dilutes the whole-block digit ratio below
    # the primary threshold (e.g. "Semi-skilled and discretionary
    # decision-making 247 20 1 4 310 29 10 35 656") is still identifiable by
    # its line structure -- one PDF text line per table cell, packed denser
    # than any real paragraph of that word count could be.
    if (
        line_density is not None
        and line_density > config.table_like_dense_line_density_threshold
        and digit_ratio >= config.table_like_dense_min_digit_ratio
        and numeric_token_count >= config.table_like_min_numeric_tokens
    ):
        return BlockType.TABLE_LIKE, True, "dense multi-line table row (numeric cells, label diluted digit ratio)"

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
