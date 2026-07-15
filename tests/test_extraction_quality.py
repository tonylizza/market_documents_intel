from market_documents.models.enums import ExtractionQuality
from market_documents.services.extraction_config import ExtractionConfig
from market_documents.services.extraction_quality import assess_page, assess_report
from market_documents.services.pdf_extraction import ExtractedPage

CONFIG = ExtractionConfig()


def _page(text: str, image_count: int = 0) -> ExtractedPage:
    return ExtractedPage(
        page_number=1, page_width=400, page_height=600, raw_text=text, image_count=image_count, blocks=[]
    )


def test_assess_page_good_for_substantial_alphabetic_text():
    text = (
        "The group delivered strong operating performance across all "
        "divisions during the reporting period, with revenue and margins "
        "both improving year on year despite a challenging macroeconomic "
        "backdrop."
    )
    result = assess_page(_page(text), CONFIG)
    assert result.extraction_quality == ExtractionQuality.GOOD
    assert result.native_text_available is True
    assert result.suspected_image_only is False


def test_assess_page_failed_for_completely_empty_page():
    result = assess_page(_page(""), CONFIG)
    assert result.extraction_quality == ExtractionQuality.FAILED
    assert result.character_count == 0
    assert result.native_text_available is False


def test_assess_page_needs_review_for_low_text_with_images():
    result = assess_page(_page("Fig 1", image_count=2), CONFIG)
    assert result.extraction_quality == ExtractionQuality.NEEDS_REVIEW
    assert result.suspected_image_only is True


def test_assess_page_needs_review_for_low_alpha_ratio_despite_length():
    text = "1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25"
    result = assess_page(_page(text), CONFIG)
    assert result.alphabetic_ratio < CONFIG.min_alpha_ratio
    assert result.extraction_quality == ExtractionQuality.NEEDS_REVIEW


def test_assess_report_good_requires_high_usable_percentage_and_no_mismatch():
    good_result = assess_page(
        _page(
            "Substantial narrative prose describing the group's financial "
            "and operational performance over the reporting period in "
            "considerable detail for lexical analysis purposes."
        ),
        CONFIG,
    )
    page_results = [good_result] * 10

    report_result = assess_report(
        page_results, expected_page_count=10, processed_page_count=10, config=CONFIG
    )
    assert report_result.extraction_quality == ExtractionQuality.GOOD
    assert report_result.review_reason is None


def test_assess_report_not_good_merely_because_pdf_opened():
    """Every page opened and produced *some* content, but not enough to be
    usable -- this must never be classified GOOD just because processing
    completed without an exception.
    """
    low_text_result = assess_page(_page("x"), CONFIG)
    page_results = [low_text_result] * 10

    report_result = assess_report(
        page_results, expected_page_count=10, processed_page_count=10, config=CONFIG
    )
    assert report_result.extraction_quality != ExtractionQuality.GOOD
    assert report_result.review_reason is not None


def test_assess_report_flags_page_count_mismatch_even_with_good_pages():
    good_result = assess_page(
        _page("Detailed narrative prose covering operational highlights and results."),
        CONFIG,
    )
    page_results = [good_result] * 9  # processed 9, expected 10

    report_result = assess_report(
        page_results, expected_page_count=10, processed_page_count=9, config=CONFIG
    )
    assert report_result.extraction_quality != ExtractionQuality.GOOD
    assert "page count mismatch" in report_result.review_reason


def test_assess_report_counts_image_only_pages():
    image_only = assess_page(_page("", image_count=3), CONFIG)
    good = assess_page(
        _page("Detailed narrative prose covering operational highlights and results in depth."),
        CONFIG,
    )
    page_results = [good] * 8 + [image_only] * 2

    report_result = assess_report(
        page_results, expected_page_count=10, processed_page_count=10, config=CONFIG
    )
    assert report_result.image_only_page_count == 2


def test_assess_report_failed_when_almost_nothing_usable():
    empty_result = assess_page(_page(""), CONFIG)
    page_results = [empty_result] * 10

    report_result = assess_report(
        page_results, expected_page_count=10, processed_page_count=10, config=CONFIG
    )
    assert report_result.extraction_quality == ExtractionQuality.FAILED
