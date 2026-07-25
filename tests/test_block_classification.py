from market_documents.models.enums import BlockType
from market_documents.services.block_classification import classify_block
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
