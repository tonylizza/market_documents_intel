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
import string
from dataclasses import dataclass

from market_documents.models.enums import BlockType
from market_documents.services.extraction_config import ExtractionConfig

_PAGE_NUMBER_DIGIT_RE = re.compile(r"(?:page\s+)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?", re.IGNORECASE)
_ROMAN_NUMERAL_RE = re.compile(r"m{0,4}(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^\s*([-•●▪*]|\d+[.)])\s+")
_URL_RE = re.compile(r"^(https?://|www\.)\S+$", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?]\s*$")

# A word with a footnote/superscript marker digit glued directly onto its
# end (e.g. "structure1", "Health1") is a PDF-extraction artifact -- the
# reference mark lost its superscript formatting and merged into the word's
# text run -- not a numeric chart/data label. It is structurally distinct
# from a real numeric token: the digit sits at the very end of a run of 3+
# letters with nothing else numeric in the token, whereas real figures
# either stand alone ("385", "2022") or lead with a unit/currency affix
# ("R450m"). Excluded from `_has_digit` so a genuine short heading like
# "Group structure" is not treated as numeric-adjacent just because a
# footnote mark rode along with it.
_FOOTNOTE_MARKER_SUFFIX_RE = re.compile(r"^[A-Za-z]{3,}\d{1,2}$")

# Generic English function words (articles, prepositions, conjunctions,
# copula/auxiliary verbs, demonstratives) -- deliberately not financial or
# report-specific vocabulary. Their presence is strong evidence of a real
# grammatical clause ("membership grew by 385 lives", "declined to 8.2%")
# rather than a bare chart/data label ("385 Denis", "26 Retail"), so any
# short block containing one of these is left alone by
# `is_short_alphanumeric_fragment` regardless of its numeric-token ratio.
_NARRATIVE_CONNECTOR_WORDS = frozenset(
    {
        "a", "an", "the",
        "and", "or", "but", "nor", "so", "yet",
        "of", "in", "on", "by", "to", "at", "as", "per",
        "with", "from", "into", "onto", "over", "under",
        "between", "across", "during", "after", "before", "than", "then",
        "is", "are", "was", "were", "be", "been", "being",
        "that", "this", "these", "those",
        "it", "its", "which", "who", "whom", "whose",
    }
)


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


def _has_digit(token: str) -> bool:
    if _FOOTNOTE_MARKER_SUFFIX_RE.match(token):
        return False
    return any(ch.isdigit() for ch in token)


def is_short_alphanumeric_fragment(stripped: str, word_count: int, config: ExtractionConfig) -> bool:
    """True for a short mixed alphanumeric chart/data-label fragment, e.g.
    "385 Denis", "26 Retail", "15.1% -2.1%", "2022 Core" -- a bare numeric
    token (a figure, a percentage, a bare year) paired with at most one
    short label token, torn out of a chart/infographic layout.

    These clear none of the existing digit-ratio thresholds: the label
    token dilutes the whole-block digit ratio below both
    `numeric_fragment_min_digit_ratio` and `table_like_min_digit_ratio`,
    and `alpha_ratio` is not low enough to trip DECORATIVE_OR_FRAGMENT
    either -- see docs/7d2a-semantic-unit-extraction-hardening.md Section 5
    for the real-corpus root-cause analysis this generalizes.

    Deliberately conservative and narrow, mirroring
    `find_table_header_fragment_indices`'s own bias toward under-firing:

    - Capped at two words/a handful of characters -- real narrative
      sentences discussing a figure are longer than a chart label, and
      capping at two words means at most one token can be the non-numeric
      label, so this never has to weigh one label word against another.
    - Excluded outright if it ends in sentence punctuation, or contains any
      generic English function word (`_NARRATIVE_CONNECTOR_WORDS`) -- both
      are evidence of a real grammatical clause, not a label.
    - Excluded if it looks like a list item (a different, already-handled
      short-block category).
    - Requires at least one token containing a digit -- this rule only
      targets the numeric-adjacent case; a bare isolated word with no
      digit at all is left to other rules (or, if none apply, PARAGRAPH).
    - The caller additionally withholds this rule whenever the block
      already reads as heading-like (shouty case, bold, or large font) --
      see the call site in `classify_block` -- so a table-of-contents entry
      like "OUR BUSINESS 6" is never reclassified out from under the
      heading-candidate rule just because it also contains a bare number.
    """
    if word_count == 0 or word_count > config.short_alphanumeric_fragment_max_words:
        return False
    if len(stripped) > config.short_alphanumeric_fragment_max_chars:
        return False
    if _SENTENCE_END_RE.search(stripped):
        return False
    if _LIST_ITEM_RE.match(stripped):
        return False

    tokens = stripped.split()
    if not any(_has_digit(token) for token in tokens):
        return False

    normalized = [token.strip(string.punctuation).lower() for token in tokens]
    if any(token in _NARRATIVE_CONNECTOR_WORDS for token in normalized if token):
        return False

    return True


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
    # The short-alphanumeric-fragment check runs only after the heading-like
    # signals above have had first refusal: a shouty or bold/large-font short
    # block (e.g. a table-of-contents entry like "OUR BUSINESS 6") must stay
    # HEADING_CANDIDATE, not be reclassified as a fragment just because it
    # also contains a bare page number -- see docs/7d2b-short-alphanumeric-
    # fragment-hardening.md for the real-corpus false positive this ordering
    # fixes.
    if not (is_heading_like_font or bool(is_bold) or is_shouty) and is_short_alphanumeric_fragment(
        stripped, word_count, config
    ):
        return BlockType.NUMERIC_FRAGMENT, True, "short alphanumeric chart/data-label fragment"

    if word_count <= config.heading_max_words and not _SENTENCE_END_RE.search(stripped) and (
        is_heading_like_font or bool(is_bold) or is_shouty
    ):
        return BlockType.HEADING_CANDIDATE, False, None

    return BlockType.PARAGRAPH, False, None


@dataclass(frozen=True)
class PageBlockGeometry:
    """The minimal per-block view needed for the table-header-fragment
    second pass: the first-pass block_type plus the same PyMuPDF bbox
    coordinates already captured during extraction. No new parsing or
    re-extraction is required -- this is a read of already-computed data."""

    block_type: BlockType
    x0: float | None
    y0: float | None
    x1: float | None
    y1: float | None


def find_table_header_fragment_indices(
    blocks: list[PageBlockGeometry], config: ExtractionConfig
) -> set[int]:
    """Identify HEADING_CANDIDATE blocks on one page that are table
    column-header/cell fragments rather than genuine narrative headings.

    Ground-truth PDF inspection (docs/passage-ground-truth-validation.md
    Section 3, "D -- Table header/cell fragments") found that reading-order
    adjacency to a TABLE_LIKE block is necessary but not sufficient: a
    genuine short heading (e.g. "Summary of results") can legitimately sit
    immediately above a table and must not be reclassified. Two additional,
    purely structural conditions distinguish a real table-header fragment:

    1. Narrow width -- the block is geometrically narrow relative to the
       widest block on the page (a column-width label or cell, not a
       full-width section heading).
    2. Clustering -- it is not alone: at least one other narrow
       HEADING_CANDIDATE block sits within a short reading-order window,
       which is the structural signature of a multi-column header row
       (e.g. "Category" / "Grade" / "Contained" as separate blocks) or a
       two-line stacked cell (e.g. "Contained" / "KCl (Mt)" split by
       PyMuPDF into two blocks for one logical column label).

    Both conditions must hold together. This is deliberately conservative:
    a single wide heading immediately preceding a table, or a single narrow
    heading with no clustered neighbor, is left classified as
    HEADING_CANDIDATE. Under-firing (missing some table-header fragments) is
    the accepted failure mode over over-firing (misclassifying a genuine
    heading), per the ground-truth investigation's own risk assessment.

    Returns the set of list indices (positions within `blocks`, which must
    already be in reading order for the page) to reclassify as
    TABLE_HEADER_FRAGMENT. Does not mutate `blocks`.
    """
    widths = [
        b.x1 - b.x0 for b in blocks if b.x0 is not None and b.x1 is not None and b.x1 > b.x0
    ]
    if not widths:
        return set()
    page_content_width = max(widths)
    if page_content_width <= 0:
        return set()

    def is_narrow(block: PageBlockGeometry) -> bool:
        if block.x0 is None or block.x1 is None or block.x1 <= block.x0:
            return False
        return (block.x1 - block.x0) <= config.table_header_fragment_max_width_ratio * page_content_width

    table_like_indices = [i for i, b in enumerate(blocks) if b.block_type == BlockType.TABLE_LIKE]
    if not table_like_indices:
        return set()

    narrow_heading_indices = [
        i
        for i, b in enumerate(blocks)
        if b.block_type == BlockType.HEADING_CANDIDATE and is_narrow(b)
    ]
    if len(narrow_heading_indices) < config.table_header_fragment_min_cluster_size:
        return set()

    window = config.table_header_fragment_adjacency_window

    reclassify: set[int] = set()
    for i in narrow_heading_indices:
        near_table = any(abs(i - t) <= window for t in table_like_indices)
        if not near_table:
            continue
        has_cluster_neighbor = any(j != i and abs(j - i) <= window for j in narrow_heading_indices)
        if has_cluster_neighbor:
            reclassify.add(i)
    return reclassify
