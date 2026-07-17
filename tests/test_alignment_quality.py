from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, ExtractionQuality
from market_documents.services.alignment_config import AlignmentConfig
from market_documents.services.alignment_quality import assess_confidence, classify_alignment, detect_disagreement

CONFIG = AlignmentConfig()


def test_classify_unchanged():
    status = classify_alignment(semantic_similarity=0.97, lexical_composite=0.95, length_ratio=1.0, config=CONFIG)
    assert status == AlignmentStatus.UNCHANGED


def test_classify_lightly_modified():
    status = classify_alignment(semantic_similarity=0.88, lexical_composite=0.60, length_ratio=0.9, config=CONFIG)
    assert status == AlignmentStatus.LIGHTLY_MODIFIED


def test_classify_substantially_modified_low_semantic():
    status = classify_alignment(semantic_similarity=0.60, lexical_composite=0.30, length_ratio=0.5, config=CONFIG)
    assert status == AlignmentStatus.SUBSTANTIALLY_MODIFIED


def test_classify_high_semantic_low_lexical_is_not_forced_substantially_modified():
    """A paraphrase (high semantic, low lexical) should not be penalized to
    SUBSTANTIALLY_MODIFIED solely because wording differs -- it still clears
    the semantic-only LIGHTLY_MODIFIED bar."""
    status = classify_alignment(semantic_similarity=0.90, lexical_composite=0.20, length_ratio=0.8, config=CONFIG)
    assert status == AlignmentStatus.LIGHTLY_MODIFIED


def test_classify_high_lexical_low_semantic_is_not_unchanged():
    """Reused boilerplate with a meaningful semantic alteration must not be
    classified UNCHANGED just because lexical overlap is high."""
    status = classify_alignment(semantic_similarity=0.50, lexical_composite=0.95, length_ratio=1.0, config=CONFIG)
    assert status != AlignmentStatus.UNCHANGED


def test_classify_unchanged_requires_length_ratio():
    status = classify_alignment(semantic_similarity=0.99, lexical_composite=0.99, length_ratio=0.5, config=CONFIG)
    assert status != AlignmentStatus.UNCHANGED


def test_detect_disagreement_high_semantic_low_lexical():
    note = detect_disagreement(semantic_similarity=0.90, lexical_composite=0.20, config=CONFIG)
    assert note is not None
    assert "paraphrase" in note


def test_detect_disagreement_low_semantic_high_lexical():
    note = detect_disagreement(semantic_similarity=0.40, lexical_composite=0.90, config=CONFIG)
    assert note is not None
    assert "boilerplate" in note


def test_detect_disagreement_none_when_evidence_agrees():
    assert detect_disagreement(semantic_similarity=0.95, lexical_composite=0.95, config=CONFIG) is None
    assert detect_disagreement(semantic_similarity=0.30, lexical_composite=0.20, config=CONFIG) is None


def test_confidence_high_with_large_margin_and_no_flags():
    result = assess_confidence(
        best_second_margin=0.20,
        disagreement=None,
        split_merge_flag=None,
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.confidence == AlignmentConfidence.HIGH
    assert result.review_reason is None


def test_confidence_low_with_small_margin():
    result = assess_confidence(
        best_second_margin=0.01,
        disagreement=None,
        split_merge_flag=None,
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.confidence == AlignmentConfidence.LOW


def test_confidence_needs_review_on_disagreement_regardless_of_margin():
    result = assess_confidence(
        best_second_margin=0.5,
        disagreement="high semantic / low lexical: likely paraphrase",
        split_merge_flag=None,
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.confidence == AlignmentConfidence.NEEDS_REVIEW
    assert "paraphrase" in result.review_reason


def test_confidence_needs_review_on_split_merge_flag():
    result = assess_confidence(
        best_second_margin=0.5,
        disagreement=None,
        split_merge_flag="likely split: also matches earlier passage",
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.confidence == AlignmentConfidence.NEEDS_REVIEW


def test_confidence_irregular_gap_downgrades_high_to_medium_not_low():
    result = assess_confidence(
        best_second_margin=0.20,
        disagreement=None,
        split_merge_flag=None,
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=96,
        config=CONFIG,
    )
    assert result.confidence == AlignmentConfidence.MEDIUM
    assert "irregular reporting gap" in result.review_reason


def test_confidence_needs_review_source_quality_propagates():
    result = assess_confidence(
        best_second_margin=0.20,
        disagreement=None,
        split_merge_flag=None,
        earlier_extraction_quality=ExtractionQuality.NEEDS_REVIEW,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.confidence == AlignmentConfidence.MEDIUM
    assert "NEEDS_REVIEW" in result.review_reason


def test_confidence_no_competing_candidate_treated_as_high_margin():
    result = assess_confidence(
        best_second_margin=None,
        disagreement=None,
        split_merge_flag=None,
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.confidence == AlignmentConfidence.HIGH
