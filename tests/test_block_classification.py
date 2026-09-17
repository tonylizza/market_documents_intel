from market_documents.models.enums import BlockType
from market_documents.services.block_classification import (
    PageBlockGeometry,
    classify_block,
    find_table_header_fragment_indices,
    is_short_alphanumeric_fragment,
)
from market_documents.services.extraction_config import ExtractionConfig

CONFIG = ExtractionConfig()


def _classify(text: str, **overrides):
    params = dict(
        is_repeated_header=False,
        is_repeated_footer=False,
        font_size=10.0,
        is_bold=None,
        page_median_font_size=10.0,
        config=CONFIG,
    )
    params.update(overrides)
    return classify_block(text, **params)


def test_repeated_header_flag_wins_regardless_of_content():
    block_type, excluded, reason = _classify("Chairman's Statement", is_repeated_header=True)
    assert block_type == BlockType.HEADER
    assert excluded is True
    assert reason is not None


def test_repeated_footer_flag_wins_regardless_of_content():
    block_type, excluded, reason = _classify("Some text", is_repeated_footer=True)
    assert block_type == BlockType.FOOTER
    assert excluded is True


def test_isolated_digit_page_number_classified_and_excluded():
    block_type, excluded, _ = _classify("42")
    assert block_type == BlockType.PAGE_NUMBER
    assert excluded is True


def test_page_of_total_pattern_classified_as_page_number():
    block_type, excluded, _ = _classify("Page 4 of 120")
    assert block_type == BlockType.PAGE_NUMBER
    assert excluded is True


def test_roman_numeral_page_number_classified():
    block_type, _, _ = _classify("xiv")
    assert block_type == BlockType.PAGE_NUMBER


def test_ordinary_word_not_misclassified_as_page_number():
    block_type, _, _ = _classify("Governance")
    assert block_type != BlockType.PAGE_NUMBER


def test_bare_url_classified_as_decorative():
    block_type, excluded, _ = _classify("https://www.example.com/reports")
    assert block_type == BlockType.DECORATIVE_OR_FRAGMENT
    assert excluded is True


def test_table_like_numeric_row_classified_and_excluded():
    block_type, excluded, _ = _classify("Revenue 1200 1100 980 850 720")
    assert block_type == BlockType.TABLE_LIKE
    assert excluded is True


def test_standalone_numeric_fragment_classified_and_excluded():
    # High digit density but only two numeric tokens -- below the
    # table-like minimum token count, so this is a bare figure pairing
    # (e.g. a stray current-year/prior-year total), not a table row.
    block_type, excluded, _ = _classify("1,245.30 890.15")
    assert block_type == BlockType.NUMERIC_FRAGMENT
    assert excluded is True


def test_list_item_with_dash_classified_and_retained():
    block_type, excluded, _ = _classify("- Strengthened balance sheet position")
    assert block_type == BlockType.LIST_ITEM
    assert excluded is False


def test_list_item_with_number_marker_classified_and_retained():
    block_type, excluded, _ = _classify("1. Improve operating margins")
    assert block_type == BlockType.LIST_ITEM
    assert excluded is False


def test_bold_larger_font_short_block_classified_as_heading():
    block_type, excluded, _ = _classify(
        "Directors' Report", font_size=16.0, is_bold=True, page_median_font_size=10.0
    )
    assert block_type == BlockType.HEADING_CANDIDATE
    assert excluded is False


def test_uppercase_short_block_classified_as_heading():
    block_type, _, _ = _classify("CORPORATE GOVERNANCE")
    assert block_type == BlockType.HEADING_CANDIDATE


def test_isolated_uppercase_letter_not_misclassified_as_heading():
    # Regression test: a single uppercase letter trivially satisfies
    # is_shouty (stripped.isupper()), which previously let it through as a
    # spurious HEADING_CANDIDATE -- the real-corpus signature of curved
    # infographic text (e.g. a circular wheel-diagram label) where each
    # glyph becomes its own block. Font/bold flags matching real infographic
    # styling, to prove the fix isn't relying on those being absent.
    block_type, excluded, reason = _classify("O", font_size=14.0, is_bold=True, page_median_font_size=10.0)
    assert block_type == BlockType.DECORATIVE_OR_FRAGMENT
    assert excluded is True
    assert "single alphabetic character" in reason


def test_isolated_lowercase_letter_also_classified_as_decorative():
    block_type, excluded, _ = _classify("e")
    assert block_type == BlockType.DECORATIVE_OR_FRAGMENT
    assert excluded is True


def test_single_roman_numeral_letter_still_classified_as_page_number():
    # The isolated-single-character rule must not shadow the existing,
    # more-specific roman-numeral page-number check for the handful of
    # letters that are also valid roman numerals.
    for letter in ["I", "V", "X", "L", "C", "D", "M"]:
        block_type, excluded, _ = _classify(letter)
        assert block_type == BlockType.PAGE_NUMBER, f"{letter!r} should still be PAGE_NUMBER"
        assert excluded is True


def test_two_character_word_unaffected_by_single_character_rule():
    # Scope check: the new rule is deliberately narrow (exactly one
    # character) -- a two-letter token is unaffected.
    block_type, _, _ = _classify("OK")
    assert block_type != BlockType.DECORATIVE_OR_FRAGMENT


def test_ordinary_paragraph_classified_and_retained():
    text = (
        "The group delivered a resilient performance in a challenging "
        "operating environment, with revenue growing steadily across all "
        "reporting segments."
    )
    block_type, excluded, reason = _classify(text)
    assert block_type == BlockType.PARAGRAPH
    assert excluded is False
    assert reason is None


def test_empty_block_classified_unknown_and_excluded():
    block_type, excluded, _ = _classify("   ")
    assert block_type == BlockType.UNKNOWN
    assert excluded is True


def test_every_block_receives_a_classification_never_raises():
    for sample in ["", "42", "!!!", "R100", "a" * 500, "😀 emoji block"]:
        block_type, excluded, _ = _classify(sample)
        assert isinstance(block_type, BlockType)
        assert isinstance(excluded, bool)


def test_overlapping_text_artifact_detected_by_extreme_line_density():
    # 20 short lines packed into a 2pt-tall bbox: a real cover-page wordmark
    # cannot physically fit 20 distinct lines in 2 points of height, so this
    # is overlapping/duplicated text objects, not prose -- regardless of its
    # (large) word count, which is why this check must run before any
    # word-count-based rule.
    text = "\n".join(["Af", "Afr", "Afro", "AfroCentric"] * 5)
    block_type, excluded, reason = _classify(text, bbox_height=2.0)
    assert block_type == BlockType.OVERLAPPING_TEXT_ARTIFACT
    assert excluded is True
    assert "line density" in reason


def test_dense_multi_line_table_row_reclassified_as_table_like():
    # A real corpus example: a text label followed by one numeric table
    # cell per line. The whole-block digit ratio (~0.25) falls below the
    # primary table-like threshold (0.3) because of the label, but the line
    # structure -- 10 lines for a handful of words -- is unmistakably a
    # table row, not a paragraph.
    text = "Semi-skilled and discretionary decision-making\n247\n20\n1\n4\n310\n29\n10\n35\n656"
    block_type, excluded, reason = _classify(text, bbox_height=30.0)
    assert block_type == BlockType.TABLE_LIKE
    assert excluded is True
    assert "dense multi-line table row" in reason


def test_tall_multi_line_block_not_misclassified_as_overlapping_artifact():
    # Same line count as a short paragraph, but a plausible paragraph-block
    # height -- line density stays low, so this must classify normally.
    text = "\n".join(
        [
            "The group delivered a resilient performance in a challenging",
            "operating environment, with revenue growing steadily across",
            "all reporting segments and cost discipline maintained",
            "throughout the year under review.",
        ]
    )
    block_type, excluded, reason = _classify(text, bbox_height=80.0)
    assert block_type == BlockType.PARAGRAPH
    assert excluded is False
    assert reason is None


def test_unknown_bbox_height_does_not_trigger_geometric_rules():
    text = "\n".join(["Af", "Afr", "Afro", "AfroCentric"] * 5)
    block_type, _, _ = _classify(text, bbox_height=None)
    assert block_type != BlockType.OVERLAPPING_TEXT_ARTIFACT


# --------------------------------------------------------------------------
# find_table_header_fragment_indices -- table-header/cell fragment second pass
#
# Fixtures below use the real block geometry cited in
# docs/passage-ground-truth-validation.md Section 3 ("D -- Table header/cell
# fragments"), so these tests are directly reproducible against the source
# PDFs named there (KP2 2023 report page 14, KP2 2025 report page 129).
# --------------------------------------------------------------------------


def _geom(block_type, x0, y0, x1, y1):
    return PageBlockGeometry(block_type=block_type, x0=x0, y0=y0, x1=x1, y1=y1)


def test_kp2_mineral_resources_table_header_row_reclassified():
    """KP2 2023 report, page 14: a two-line multi-column header row
    ("Category Million Tonnes" / "Grade" / "KCl %" / "Contained" /
    "KCl (Mt)") immediately preceding numeric TABLE_LIKE rows. Every header
    fragment should be identified for reclassification."""
    blocks = [
        _geom(BlockType.PARAGRAPH, 60, 100, 460, 170),  # a normal wide body paragraph sets page width
        _geom(BlockType.HEADING_CANDIDATE, 97, 181, 283, 205),  # "Category Million Tonnes"
        _geom(BlockType.HEADING_CANDIDATE, 299, 181, 324, 194),  # "Grade"
        _geom(BlockType.HEADING_CANDIDATE, 300, 192, 323, 205),  # "KCl %"
        _geom(BlockType.HEADING_CANDIDATE, 337, 181, 378, 194),  # "Contained"
        _geom(BlockType.HEADING_CANDIDATE, 341, 192, 374, 205),  # "KCl (Mt)"
        _geom(BlockType.TABLE_LIKE, 97, 210, 460, 240),  # numeric mineral-resource row
        _geom(BlockType.TABLE_LIKE, 97, 241, 460, 271),  # numeric mineral-resource row
    ]
    result = find_table_header_fragment_indices(blocks, CONFIG)
    assert result == {1, 2, 3, 4, 5}


def test_kp2_currency_unit_subheader_reclassified():
    """KP2 2025 report, page 129: "Dec 2025"/"USD" and "Dec 2024"/"USD"
    column sub-headers, each a separate PyMuPDF block, above a numeric
    KMP-disclosure table."""
    blocks = [
        _geom(BlockType.PARAGRAPH, 60, 100, 460, 170),
        _geom(BlockType.HEADING_CANDIDATE, 213, 300, 270, 314),  # "Dec 2025"
        _geom(BlockType.HEADING_CANDIDATE, 226, 316, 250, 328),  # "USD"
        _geom(BlockType.HEADING_CANDIDATE, 300, 300, 357, 314),  # "Dec 2024"
        _geom(BlockType.HEADING_CANDIDATE, 313, 316, 337, 328),  # "USD"
        _geom(BlockType.TABLE_LIKE, 97, 330, 460, 360),
    ]
    result = find_table_header_fragment_indices(blocks, CONFIG)
    assert result == {1, 2, 3, 4}


def test_genuine_wide_heading_above_table_not_reclassified():
    """A genuine section heading ("Summary of results") spans most of the
    page's content width and has no clustered narrow neighbor -- it must
    survive as HEADING_CANDIDATE even though a table follows immediately."""
    blocks = [
        _geom(BlockType.HEADING_CANDIDATE, 60, 100, 440, 120),  # "Summary of results" -- wide
        _geom(BlockType.TABLE_LIKE, 60, 130, 440, 160),
        _geom(BlockType.TABLE_LIKE, 60, 161, 440, 191),
    ]
    result = find_table_header_fragment_indices(blocks, CONFIG)
    assert result == set()


def test_isolated_narrow_heading_near_table_not_reclassified_without_cluster():
    """A single narrow heading-candidate near a table, with no other narrow
    heading-candidate nearby, is left alone -- clustering evidence is
    required, not just narrowness plus adjacency."""
    blocks = [
        _geom(BlockType.PARAGRAPH, 60, 60, 440, 90),
        _geom(BlockType.HEADING_CANDIDATE, 300, 100, 340, 114),  # lone narrow fragment, e.g. "Grade"
        _geom(BlockType.TABLE_LIKE, 60, 120, 440, 150),
    ]
    result = find_table_header_fragment_indices(blocks, CONFIG)
    assert result == set()


def test_genuine_short_heading_with_no_table_on_page_not_reclassified():
    """"Committee" -- a genuine one-word governance subheading with no
    table anywhere on the page -- must never be reclassified."""
    blocks = [
        _geom(BlockType.HEADING_CANDIDATE, 60, 100, 120, 114),  # "Committee"
        _geom(BlockType.PARAGRAPH, 60, 120, 440, 300),
    ]
    result = find_table_header_fragment_indices(blocks, CONFIG)
    assert result == set()


def test_narrow_headings_clustered_but_far_from_any_table_not_reclassified():
    """Two narrow, clustered heading-candidates that are nowhere near a
    TABLE_LIKE block (outside the adjacency window) are left alone."""
    blocks = (
        [_geom(BlockType.PARAGRAPH, 60, 60, 440, 90)]
        + [_geom(BlockType.HEADING_CANDIDATE, 100 + i * 5, 100, 120 + i * 5, 114) for i in range(3)]
        + [_geom(BlockType.PARAGRAPH, 60, 120, 440, 200) for _ in range(10)]
        + [_geom(BlockType.TABLE_LIKE, 60, 900, 440, 930)]
    )
    result = find_table_header_fragment_indices(blocks, CONFIG)
    assert result == set()


def test_no_table_like_block_on_page_short_circuits():
    blocks = [
        _geom(BlockType.HEADING_CANDIDATE, 100, 100, 120, 114),
        _geom(BlockType.HEADING_CANDIDATE, 130, 100, 150, 114),
    ]
    assert find_table_header_fragment_indices(blocks, CONFIG) == set()


def test_no_geometry_available_short_circuits():
    blocks = [
        PageBlockGeometry(block_type=BlockType.HEADING_CANDIDATE, x0=None, y0=None, x1=None, y1=None),
        PageBlockGeometry(block_type=BlockType.TABLE_LIKE, x0=None, y0=None, x1=None, y1=None),
    ]
    assert find_table_header_fragment_indices(blocks, CONFIG) == set()


# --------------------------------------------------------------------------
# Track 7D.2b -- short alphanumeric chart/data-label fragment hardening.
#
# Fixtures are the real ACT 2021/2022 corpus blocks (canonical_blocks raw
# text, confirmed via direct DB inspection during this track) that leaked
# into `healthcare_services_review`'s persisted source_text, plus nearby
# real narrative from the same pages/reports used as false-positive guards.
# --------------------------------------------------------------------------


def test_number_plus_short_label_classified_as_fragment():
    # Real ACT 2021 corpus block (p63): a chart figure paired with a
    # one-word data-series label.
    block_type, excluded, reason = _classify("385 Denis")
    assert block_type == BlockType.NUMERIC_FRAGMENT
    assert excluded is True
    assert reason == "short alphanumeric chart/data-label fragment"


def test_multiple_percentage_tokens_classified_as_fragment():
    # Real ACT 2022 corpus block (p62): two percentage figures with no
    # label text at all.
    block_type, excluded, _ = _classify("15.1%\n-2.1%")
    assert block_type == BlockType.NUMERIC_FRAGMENT
    assert excluded is True


def test_year_plus_short_label_classified_as_fragment():
    # Real ACT 2021 corpus block (p63): a bare year paired with the start
    # of a parenthetical chart annotation.
    block_type, excluded, _ = _classify("2021\n(excluding")
    assert block_type == BlockType.NUMERIC_FRAGMENT
    assert excluded is True


def test_currency_unit_prefixed_figure_with_label_classified_as_fragment():
    block_type, excluded, _ = _classify("R450m Revenue")
    assert block_type == BlockType.NUMERIC_FRAGMENT
    assert excluded is True


def test_legitimate_short_sentence_with_percentage_not_reclassified():
    # Contains the generic connector "by" -- real grammatical structure,
    # not a bare label -- and is also too long for the word cap.
    block_type, excluded, _ = _classify("revenue increased by 15%")
    assert block_type != BlockType.NUMERIC_FRAGMENT
    assert excluded is False


def test_legitimate_sentence_with_year_not_reclassified():
    text = "Revenue increased by 15.1% during the year."
    block_type, excluded, _ = _classify(text)
    assert block_type == BlockType.PARAGRAPH
    assert excluded is False


def test_ordinary_heading_not_reclassified_as_fragment():
    block_type, _, _ = _classify("CORPORATE GOVERNANCE")
    assert block_type == BlockType.HEADING_CANDIDATE


def test_bold_large_font_short_block_with_number_stays_heading_not_fragment():
    # A table-of-contents entry ("OUR BUSINESS 6") is shouty and would
    # otherwise satisfy the fragment shape (one short label + one bare
    # number) -- heading-like signals must win first.
    block_type, excluded, _ = _classify("OUR BUSINESS \n6")
    assert block_type == BlockType.HEADING_CANDIDATE
    assert excluded is False


def test_footnote_text_not_reclassified():
    text = "Note 12: Refer to the 2022 annual financial statements for detail."
    block_type, excluded, _ = _classify(text)
    assert block_type == BlockType.PARAGRAPH
    assert excluded is False


def test_word_with_glued_footnote_marker_digit_not_reclassified():
    # Real ACT corpus block, recurring across years: a genuine short
    # heading ("Group structure") where PyMuPDF merged a footnote/
    # superscript reference-mark digit directly onto the last word with no
    # space -- not a real numeric token.
    block_type, excluded, _ = _classify("Group structure1")
    assert block_type != BlockType.NUMERIC_FRAGMENT
    assert excluded is False


def test_existing_numeric_fragment_behavior_still_valid():
    # Pre-existing NUMERIC_FRAGMENT case (high digit ratio, low token
    # count) must remain unaffected by the new rule.
    block_type, excluded, _ = _classify("1,245.30 890.15")
    assert block_type == BlockType.NUMERIC_FRAGMENT
    assert excluded is True


def test_existing_table_like_behavior_still_valid():
    block_type, excluded, _ = _classify("Revenue 1200 1100 980 850 720")
    assert block_type == BlockType.TABLE_LIKE
    assert excluded is True


# --------------------------------------------------------------------------
# is_short_alphanumeric_fragment -- direct unit tests of the pure helper.
# --------------------------------------------------------------------------


def _is_fragment(text: str) -> bool:
    return is_short_alphanumeric_fragment(text.strip(), len(text.strip().split()), CONFIG)


def test_helper_true_for_known_fragment_shapes():
    for text in ["385 Denis", "26 Retail", "2022 Core", "15.1% -2.1%"]:
        assert _is_fragment(text), text


def test_helper_false_when_sentence_punctuation_present():
    assert _is_fragment("Revenue rose 15%.") is False


def test_helper_false_when_connector_word_present():
    assert _is_fragment("by 15%") is False


def test_helper_false_when_no_digit_token_present():
    assert _is_fragment("Denis") is False


def test_helper_false_for_list_item_shape():
    assert _is_fragment("2) Retail") is False


def test_helper_false_beyond_word_cap():
    assert _is_fragment("2022 Core Segment") is False
