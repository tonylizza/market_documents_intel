from market_documents.models.enums import DiffMode, ExtractionQuality, SimilarityResultQuality
from market_documents.services.similarity_config import SimilarityConfig
from market_documents.services.similarity_metrics import LengthChangeFeatures, MetricSet
from market_documents.services.similarity_quality import assess_similarity

CONFIG = SimilarityConfig(
    min_words_for_review=200,
    max_length_ratio_for_review=3.0,
    max_gap_months_for_review=18,
    metric_disagreement_threshold=0.4,
)


def _metrics(
    cosine=0.8, jaccard=0.7, diff=0.75, edit=0.72, diff_mode=DiffMode.FULL_NO_AUTOJUNK, diff_duration_ms=5.0
) -> MetricSet:
    return MetricSet(
        lexical_cosine_similarity=cosine,
        jaccard_similarity=jaccard,
        diff_similarity=diff,
        diff_mode=diff_mode,
        diff_duration_ms=diff_duration_ms,
        edit_similarity=edit,
    )


def _length(earlier_words=1000, later_words=1050) -> LengthChangeFeatures:
    return LengthChangeFeatures(
        earlier_word_count=earlier_words,
        later_word_count=later_words,
        word_count_change=later_words - earlier_words,
        word_count_change_ratio=(later_words - earlier_words) / earlier_words if earlier_words else None,
        earlier_character_count=earlier_words * 6,
        later_character_count=later_words * 6,
        character_count_change=(later_words - earlier_words) * 6,
        character_count_change_ratio=(later_words - earlier_words) / earlier_words if earlier_words else None,
    )


def test_clean_pair_is_good_and_primary_eligible():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.GOOD
    assert result.review_reason is None
    assert result.primary_analysis_eligible is True
    assert result.primary_analysis_exclusion_reason is None


def test_usable_extraction_input_yields_usable_quality_but_still_primary_eligible():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.USABLE,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.USABLE
    assert result.review_reason is not None
    assert "extraction quality below GOOD" in result.review_reason
    assert result.primary_analysis_eligible is True


def test_needs_review_extraction_input_yields_needs_review_and_excludes_from_primary():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.NEEDS_REVIEW,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "NEEDS_REVIEW" in result.review_reason
    assert result.primary_analysis_eligible is False
    assert result.primary_analysis_exclusion_reason == "result quality is NEEDS_REVIEW"


def test_transition_pair_excluded_from_primary_even_when_good_quality():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=True,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.GOOD
    assert result.primary_analysis_eligible is False
    assert result.primary_analysis_exclusion_reason == "transition-period pair excluded from primary analysis by default"


def test_transition_pair_is_still_scored_not_failed():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=True,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality != SimilarityResultQuality.FAILED


def test_short_document_triggers_review():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(earlier_words=50, later_words=1050),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "below review threshold" in result.review_reason
    assert result.primary_analysis_eligible is False


def test_extreme_length_ratio_triggers_review():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(earlier_words=1000, later_words=5000),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "length ratio" in result.review_reason


def test_large_reporting_gap_triggers_review():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=36,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "reporting gap" in result.review_reason


def test_metric_disagreement_triggers_review():
    result = assess_similarity(
        metrics=_metrics(cosine=0.95, jaccard=0.90, diff=0.40, edit=0.85),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "disagreement" in result.review_reason


def test_metric_agreement_within_tolerance_does_not_trigger_review():
    result = assess_similarity(
        metrics=_metrics(cosine=0.80, jaccard=0.75, diff=0.78, edit=0.72),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.GOOD


def test_all_metrics_failed_yields_failed_quality():
    result = assess_similarity(
        metrics=MetricSet(
            lexical_cosine_similarity=None,
            jaccard_similarity=None,
            diff_similarity=None,
            diff_mode=DiffMode.FULL_NO_AUTOJUNK,
            diff_duration_ms=None,
            edit_similarity=None,
        ),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.FAILED
    assert result.primary_analysis_eligible is False
    assert result.primary_analysis_exclusion_reason == "all similarity metrics failed"


def test_some_metrics_failed_yields_needs_review_not_failed():
    result = assess_similarity(
        metrics=MetricSet(
            lexical_cosine_similarity=0.8,
            jaccard_similarity=None,
            diff_similarity=0.75,
            diff_mode=DiffMode.FULL_NO_AUTOJUNK,
            diff_duration_ms=5.0,
            edit_similarity=0.72,
        ),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "jaccard_similarity" in result.review_reason
    assert result.primary_analysis_eligible is False


def test_diff_skipped_for_token_limit_is_informational_not_review_triggering():
    """A diff omitted because the document exceeded the token threshold is a
    metric-availability fact, not a quality problem: with all other metrics
    clean, the result must stay GOOD, not drop to NEEDS_REVIEW the way a
    genuine metric failure would.
    """
    result = assess_similarity(
        metrics=_metrics(diff=None, diff_mode=DiffMode.SKIPPED_TOKEN_LIMIT, diff_duration_ms=None),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.GOOD
    assert result.primary_analysis_eligible is True
    assert result.review_reason == "diff_similarity omitted: token count exceeds configured limit"


def test_diff_skipped_combined_with_a_real_review_trigger_still_flags():
    """The informational skip note coexists with genuine review reasons --
    it doesn't suppress them, and a real trigger still degrades quality.
    """
    result = assess_similarity(
        metrics=_metrics(diff=None, diff_mode=DiffMode.SKIPPED_TOKEN_LIMIT, diff_duration_ms=None),
        length_features=_length(earlier_words=50, later_words=60),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "below review threshold" in result.review_reason
    assert "diff_similarity omitted" in result.review_reason


def test_diff_none_without_skip_mode_still_counts_as_a_failed_metric():
    """Distinguishes a genuine diff failure (e.g. the both-empty edge case,
    diff_mode still FULL_NO_AUTOJUNK) from a deliberate size-based skip --
    only the latter is informational-only.
    """
    result = assess_similarity(
        metrics=_metrics(diff=None, diff_mode=DiffMode.FULL_NO_AUTOJUNK, diff_duration_ms=None),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.GOOD,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "diff_similarity" in result.review_reason
    assert "metric(s) undefined" in result.review_reason


def test_usable_extraction_quality_alone_is_not_flagged_as_review():
    """USABLE extraction quality is legitimate and must not, by itself,
    produce a review reason string implying something is wrong -- it only
    caps the result at USABLE quality via the trailing explanatory note.
    """
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(),
        earlier_extraction_quality=ExtractionQuality.USABLE,
        later_extraction_quality=ExtractionQuality.USABLE,
        is_transition=False,
        gap_months=12,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.USABLE
    assert result.primary_analysis_eligible is True
    # The one reason present explains the USABLE tier, not a review flag.
    assert result.review_reason == "source extraction quality below GOOD on at least one side"


def test_multiple_reasons_are_joined():
    result = assess_similarity(
        metrics=_metrics(),
        length_features=_length(earlier_words=50, later_words=60),
        earlier_extraction_quality=ExtractionQuality.NEEDS_REVIEW,
        later_extraction_quality=ExtractionQuality.GOOD,
        is_transition=True,
        gap_months=36,
        config=CONFIG,
    )
    assert result.quality == SimilarityResultQuality.NEEDS_REVIEW
    assert "below review threshold" in result.review_reason
    assert "NEEDS_REVIEW" in result.review_reason
    assert "reporting gap" in result.review_reason
    # Transition status is tracked separately via the exclusion reason, not
    # folded into review_reason -- see similarity_quality.py. It also takes
    # precedence over the quality-based exclusion reason.
    assert result.primary_analysis_exclusion_reason == "transition-period pair excluded from primary analysis by default"
