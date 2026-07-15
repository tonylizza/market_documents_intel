from market_documents.services.text_cleaning import (
    clean_text,
    collapse_whitespace,
    join_wrapped_lines,
    normalize_unicode,
    repair_hyphenation,
    strip_control_characters,
)


def test_normalize_unicode_applies_nfkc():
    # U+FB01 LATIN SMALL LIGATURE FI decomposes to "fi" under NFKC.
    assert normalize_unicode("ﬁnancial") == "financial"


def test_strip_control_characters_removes_null_bytes():
    assert strip_control_characters("revenue\x00 growth") == "revenue growth"


def test_strip_control_characters_preserves_newlines_and_tabs():
    text = "line one\nline two\tindented"
    assert strip_control_characters(text) == text


def test_repair_hyphenation_joins_lowercase_split_word():
    assert repair_hyphenation("finan-\ncial performance") == "financial performance"


def test_repair_hyphenation_preserves_proper_noun_compound():
    assert repair_hyphenation("South-\nAfrican operations") == "South-\nAfrican operations"


def test_repair_hyphenation_preserves_numeric_range():
    assert repair_hyphenation("the 2023-\n2024 financial year") == "the 2023-\n2024 financial year"


def test_repair_hyphenation_preserves_established_compound_without_linebreak():
    assert repair_hyphenation("year-on-year growth") == "year-on-year growth"
    assert repair_hyphenation("non-current liabilities") == "non-current liabilities"


def test_join_wrapped_lines_replaces_single_newline_with_space():
    assert join_wrapped_lines("This sentence\nwraps here.") == "This sentence wraps here."


def test_join_wrapped_lines_preserves_paragraph_breaks():
    result = join_wrapped_lines("Paragraph one.\n\nParagraph two.")
    assert result == "Paragraph one.\n\nParagraph two."


def test_join_wrapped_lines_collapses_excessive_blank_lines():
    result = join_wrapped_lines("Paragraph one.\n\n\n\n\nParagraph two.")
    assert result == "Paragraph one.\n\nParagraph two."


def test_collapse_whitespace_collapses_repeated_spaces():
    assert collapse_whitespace("too   many    spaces") == "too many spaces"


def test_clean_text_full_pipeline_repairs_hyphenation_and_whitespace():
    raw = "The  group's  finan-\ncial performance   improved.\n\n\nRevenue grew by 12%."
    cleaned = clean_text(raw)
    assert "financial performance" in cleaned
    assert "  " not in cleaned
    assert "\n\n\n" not in cleaned


def test_clean_text_preserves_wording_and_punctuation():
    raw = "Gross margin increased to 45.2%, up from 41.8% in the prior year."
    assert clean_text(raw) == raw


def test_clean_text_strips_leading_and_trailing_whitespace():
    assert clean_text("   padded text   ") == "padded text"
