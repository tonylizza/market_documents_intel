"""Page-level and report-level extraction quality diagnostics.

All thresholds come from `ExtractionConfig` -- nothing here is an
unexplained magic number. A run is never classified GOOD merely because
the PDF opened: GOOD additionally requires a high usable-page percentage
and the absence of every other review trigger (page-count mismatch,
image-only pages, excess empty or low-text pages).
"""

from dataclasses import dataclass

from market_documents.models.enums import ExtractionQuality
from market_documents.services.extraction_config import ExtractionConfig
from market_documents.services.pdf_extraction import ExtractedPage


@dataclass(frozen=True)
class PageQualityResult:
    character_count: int
    word_count: int
    block_count: int
    alphabetic_ratio: float
    numeric_ratio: float
    native_text_available: bool
    suspected_image_only: bool
    extraction_quality: ExtractionQuality


@dataclass(frozen=True)
class ReportQualityResult:
    usable_page_count: int
    usable_page_percentage: float
    low_text_page_count: int
    image_only_page_count: int
    total_word_count: int
    extraction_quality: ExtractionQuality
    review_reason: str | None


def assess_page(page: ExtractedPage, config: ExtractionConfig) -> PageQualityResult:
    text = page.raw_text
    character_count = len(text)
    word_count = len(text.split())
    block_count = len(page.blocks)
    alpha_chars = sum(ch.isalpha() for ch in text)
    digit_chars = sum(ch.isdigit() for ch in text)
    alphabetic_ratio = alpha_chars / character_count if character_count else 0.0
    numeric_ratio = digit_chars / character_count if character_count else 0.0

    native_text_available = word_count > 0
    is_low_text = character_count < config.min_chars_for_usable_page or (
        character_count > 0 and alphabetic_ratio < config.min_alpha_ratio
    )
    suspected_image_only = not native_text_available or (is_low_text and page.image_count > 0)

    if character_count == 0:
        quality = ExtractionQuality.FAILED
    elif suspected_image_only or is_low_text:
        quality = ExtractionQuality.NEEDS_REVIEW
    elif alphabetic_ratio >= config.min_alpha_ratio and character_count >= config.min_chars_for_usable_page * 3:
        quality = ExtractionQuality.GOOD
    else:
        quality = ExtractionQuality.USABLE

    return PageQualityResult(
        character_count=character_count,
        word_count=word_count,
        block_count=block_count,
        alphabetic_ratio=alphabetic_ratio,
        numeric_ratio=numeric_ratio,
        native_text_available=native_text_available,
        suspected_image_only=suspected_image_only,
        extraction_quality=quality,
    )


def assess_report(
    page_results: list[PageQualityResult],
    *,
    expected_page_count: int,
    processed_page_count: int,
    config: ExtractionConfig,
) -> ReportQualityResult:
    reasons: list[str] = []

    usable_page_count = sum(
        1
        for r in page_results
        if r.extraction_quality in (ExtractionQuality.GOOD, ExtractionQuality.USABLE)
    )
    low_text_page_count = sum(
        1
        for r in page_results
        if r.extraction_quality in (ExtractionQuality.NEEDS_REVIEW, ExtractionQuality.FAILED)
    )
    image_only_page_count = sum(1 for r in page_results if r.suspected_image_only)
    empty_page_count = sum(1 for r in page_results if r.character_count == 0)
    total_word_count = sum(r.word_count for r in page_results)

    usable_page_percentage = usable_page_count / processed_page_count if processed_page_count else 0.0
    empty_page_ratio = empty_page_count / processed_page_count if processed_page_count else 0.0
    low_text_ratio = low_text_page_count / processed_page_count if processed_page_count else 0.0

    if expected_page_count != processed_page_count:
        reasons.append(
            f"page count mismatch (expected {expected_page_count}, processed {processed_page_count})"
        )
    if image_only_page_count:
        reasons.append(f"{image_only_page_count} likely image-only page(s)")
    if empty_page_ratio > config.max_empty_page_ratio:
        reasons.append(f"{empty_page_count} empty page(s) exceeds tolerance")
    if low_text_ratio > config.low_text_page_tolerance:
        reasons.append(f"{low_text_page_count} low-text page(s) exceeds tolerance")

    if usable_page_percentage >= config.good_quality_usable_page_threshold and not reasons:
        quality = ExtractionQuality.GOOD
    elif usable_page_percentage >= config.usable_quality_usable_page_threshold:
        quality = ExtractionQuality.USABLE
    elif usable_page_percentage >= config.needs_review_usable_page_threshold:
        quality = ExtractionQuality.NEEDS_REVIEW
    else:
        quality = ExtractionQuality.FAILED

    if quality != ExtractionQuality.GOOD and not reasons:
        reasons.append(f"usable-page percentage {usable_page_percentage:.0%} below GOOD threshold")

    return ReportQualityResult(
        usable_page_count=usable_page_count,
        usable_page_percentage=usable_page_percentage,
        low_text_page_count=low_text_page_count,
        image_only_page_count=image_only_page_count,
        total_word_count=total_word_count,
        extraction_quality=quality,
        review_reason="; ".join(reasons) if reasons else None,
    )
