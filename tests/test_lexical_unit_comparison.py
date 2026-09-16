"""Pure tests for `services.lexical_unit_comparison` (Track 7C.3): persisted
metrics must be exactly what the existing, already-validated metric
functions compute -- no reimplemented math.
"""

from market_documents.services.lexical_unit_comparison import compute_lexical_metrics
from market_documents.services.similarity_metrics import (
    diff_similarity,
    edit_similarity,
    jaccard_similarity,
    lexical_cosine_similarity,
)
from market_documents.services.similarity_tokenization import tokenize

EARLIER = "The gross margin is dependent on the product and geographic mix of sales, market conditions and exchange rates."
LATER = (
    "The gross margin is dependent on the product and geographic mix of sales, market conditions and exchange rates. "
    "Margin improved due to favourable currency effects."
)


def test_metrics_match_direct_calls_to_existing_metric_functions():
    metrics = compute_lexical_metrics(EARLIER, LATER)

    tokens_a = tokenize(EARLIER)
    tokens_b = tokenize(LATER)

    assert metrics.lexical_cosine_similarity == lexical_cosine_similarity(tokens_a, tokens_b)
    assert metrics.unigram_jaccard == jaccard_similarity(tokens_a, tokens_b, shingle_size=1)
    assert metrics.bigram_jaccard == jaccard_similarity(tokens_a, tokens_b, shingle_size=2)
    assert metrics.edit_similarity == edit_similarity(tokens_a, tokens_b)
    assert metrics.sequence_similarity == diff_similarity(tokens_a, tokens_b)


def test_word_counts_are_tokenizer_based_and_consistent():
    metrics = compute_lexical_metrics(EARLIER, LATER)

    assert metrics.earlier_word_count == len(tokenize(EARLIER))
    assert metrics.later_word_count == len(tokenize(LATER))
    assert metrics.word_count_change == metrics.later_word_count - metrics.earlier_word_count


def test_word_count_change_pct_computed_from_earlier_count():
    metrics = compute_lexical_metrics(EARLIER, LATER)

    expected_pct = (metrics.word_count_change / metrics.earlier_word_count) * 100.0
    assert metrics.word_count_change_pct == expected_pct


def test_word_count_change_pct_is_none_when_earlier_is_empty():
    metrics = compute_lexical_metrics("", "some later text here")

    assert metrics.earlier_word_count == 0
    assert metrics.word_count_change_pct is None


def test_undefined_metrics_stay_none_not_fabricated():
    metrics = compute_lexical_metrics("", "")

    assert metrics.lexical_cosine_similarity is None
    assert metrics.unigram_jaccard is None
    assert metrics.bigram_jaccard is None
    assert metrics.edit_similarity is None
    assert metrics.sequence_similarity is None
    assert metrics.earlier_word_count == 0
    assert metrics.later_word_count == 0
    assert metrics.word_count_change == 0
    assert metrics.word_count_change_pct is None


def test_identical_texts_produce_identical_similarity_of_one():
    metrics = compute_lexical_metrics(EARLIER, EARLIER)

    assert metrics.lexical_cosine_similarity == 1.0
    assert metrics.unigram_jaccard == 1.0
    assert metrics.bigram_jaccard == 1.0
    assert metrics.edit_similarity == 1.0
    assert metrics.sequence_similarity == 1.0
    assert metrics.word_count_change == 0
    assert metrics.word_count_change_pct == 0.0
