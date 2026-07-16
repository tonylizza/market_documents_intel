import math
import time

from market_documents.models.enums import DiffMode
from market_documents.services.similarity_metrics import (
    compute_length_change_features,
    compute_metrics,
    diff_similarity,
    diff_similarity_with_mode,
    edit_similarity,
    jaccard_similarity,
    lexical_cosine_similarity,
)
from market_documents.services.similarity_tokenization import tokenize

# ---------------------------------------------------------------------------
# Lexical cosine similarity
# ---------------------------------------------------------------------------


def test_cosine_identical_documents_returns_one():
    tokens = tokenize("the group reported strong revenue growth this year")
    assert lexical_cosine_similarity(tokens, tokens) == 1.0


def test_cosine_completely_disjoint_documents_returns_zero():
    a = tokenize("apples bananas cherries")
    b = tokenize("dragons elephants foxes")
    assert lexical_cosine_similarity(a, b) == 0.0


def test_cosine_partial_overlap_is_bounded_intermediate():
    a = tokenize("revenue increased due to strong demand in the region")
    b = tokenize("revenue decreased due to weak demand in another region")
    score = lexical_cosine_similarity(a, b)
    assert score is not None
    assert 0.0 < score < 1.0


def test_cosine_empty_tokens_returns_none():
    assert lexical_cosine_similarity([], ["revenue", "growth"]) is None
    assert lexical_cosine_similarity(["revenue", "growth"], []) is None
    assert lexical_cosine_similarity([], []) is None


def test_cosine_vocabulary_is_union_of_the_two_documents():
    a = ["alpha", "beta"]
    b = ["beta", "gamma"]
    # Sanity: cosine should be computable (nonzero norms) and bounded, which
    # requires the shared vocabulary to include every term from both sides
    # (alpha, beta, gamma) -- if it didn't, dot products would be wrong.
    score = lexical_cosine_similarity(a, b)
    assert score is not None
    assert 0.0 < score < 1.0


def test_cosine_is_deterministic():
    a = tokenize("the annual report discusses risk factors and liquidity")
    b = tokenize("the annual report discusses market risk and capital")
    assert lexical_cosine_similarity(a, b) == lexical_cosine_similarity(a, b)


def test_cosine_is_pair_local_adding_unrelated_document_does_not_change_score():
    """No corpus-wide fitting: the vocabulary and score for one pair must be
    computable from only those two documents, with no shared/cached state.
    """
    a = tokenize("the group increased revenue and reduced costs")
    b = tokenize("the group decreased revenue and increased costs")
    baseline = lexical_cosine_similarity(a, b)

    unrelated = tokenize("an entirely unrelated third document about something else")
    # Scoring an unrelated pair first must not perturb any shared/global state.
    lexical_cosine_similarity(a, unrelated)
    lexical_cosine_similarity(b, unrelated)

    assert lexical_cosine_similarity(a, b) == baseline


def _linear_tf_cosine(tokens_a: list[str], tokens_b: list[str]) -> float | None:
    """Reference cosine using raw (linear) term frequency, for comparison
    against the production sublinear implementation -- not used anywhere
    outside this test file.
    """
    from collections import Counter

    vocab = sorted(set(tokens_a) | set(tokens_b))
    counts_a, counts_b = Counter(tokens_a), Counter(tokens_b)
    vec_a = [counts_a[t] for t in vocab]
    vec_b = [counts_b[t] for t in vocab]
    norm_a = math.sqrt(sum(v * v for v in vec_a))
    norm_b = math.sqrt(sum(v * v for v in vec_b))
    if norm_a == 0 or norm_b == 0:
        return None
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    return dot / (norm_a * norm_b)


def test_cosine_sublinear_tf_dampens_repeated_terms_vs_linear():
    """A document that repeats one shared term many times should not
    dominate the comparison the way raw (linear) term frequency would --
    sublinear scaling (1 + log(c)) grows much slower than c itself, so the
    sublinear score must sit below what linear tf would produce for the
    same heavily-repeated-term scenario.
    """
    repeated_a = tokenize("revenue " * 50 + "profit")
    repeated_b = tokenize("revenue " * 50 + "loss")

    sublinear_score = lexical_cosine_similarity(repeated_a, repeated_b)
    linear_score = _linear_tf_cosine(repeated_a, repeated_b)

    assert sublinear_score is not None and linear_score is not None
    assert sublinear_score < linear_score


def test_cosine_bounded_between_zero_and_one():
    a = tokenize("the company reported revenue of one hundred million dollars")
    b = tokenize("the company reported revenue of two hundred million dollars")
    score = lexical_cosine_similarity(a, b)
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_cosine_unigram_representation_is_order_independent():
    """Sanity check that the current implementation is a bag-of-words
    (order does not matter) -- distinguishes it from diff/edit metrics.
    """
    a = tokenize("alpha beta gamma")
    b = tokenize("gamma beta alpha")
    assert lexical_cosine_similarity(a, b) == 1.0


# ---------------------------------------------------------------------------
# Jaccard similarity (word-bigram shingles)
# ---------------------------------------------------------------------------


def test_jaccard_identical_nonempty_sets_returns_one():
    tokens = tokenize("the group reported strong revenue growth")
    assert jaccard_similarity(tokens, tokens) == 1.0


def test_jaccard_bounded_between_zero_and_one():
    a = tokenize("revenue increased due to strong demand")
    b = tokenize("revenue decreased due to weak demand")
    score = jaccard_similarity(a, b)
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_jaccard_both_empty_returns_none():
    assert jaccard_similarity([], []) is None


def test_jaccard_too_few_tokens_for_shingles_returns_none():
    assert jaccard_similarity(["only"], ["only"]) is None


def test_jaccard_one_side_empty_returns_zero():
    a = tokenize("revenue growth continued")
    assert jaccard_similarity(a, []) == 0.0


def test_jaccard_duplicate_tokens_do_not_change_score():
    a = tokenize("revenue growth revenue growth revenue growth")
    b = tokenize("revenue growth")
    # {"revenue growth"} shingle set is identical either way (dedup via set).
    assert jaccard_similarity(a, a) == jaccard_similarity(b, b) == 1.0


def test_jaccard_captures_phrase_overlap_not_just_unigram_overlap():
    # Same unigram vocabulary, different word order -> different bigrams.
    a = tokenize("strong revenue weak profit")
    b = tokenize("weak revenue strong profit")
    cosine = lexical_cosine_similarity(a, b)
    jaccard = jaccard_similarity(a, b)
    assert cosine == 1.0  # identical bag-of-words
    assert jaccard is not None and jaccard < 1.0  # different phrase structure


def test_jaccard_configurable_shingle_size():
    a = tokenize("alpha beta gamma delta")
    b = tokenize("alpha beta gamma delta")
    assert jaccard_similarity(a, b, shingle_size=3) == 1.0


# ---------------------------------------------------------------------------
# Diff similarity (token-sequence difflib.SequenceMatcher)
# ---------------------------------------------------------------------------


def test_diff_identical_documents_returns_one():
    tokens = tokenize("the group reported strong revenue growth this year")
    assert diff_similarity(tokens, tokens) == 1.0


def test_diff_bounded_between_zero_and_one():
    a = tokenize("revenue increased due to strong demand")
    b = tokenize("costs decreased due to efficiency gains")
    score = diff_similarity(a, b)
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_diff_both_empty_returns_none():
    assert diff_similarity([], []) is None


def test_diff_one_side_empty_returns_zero():
    a = tokenize("revenue growth continued")
    assert diff_similarity(a, []) == 0.0


def test_diff_detects_insertion():
    base = tokenize("the group reported strong revenue growth")
    inserted = tokenize("the group reported strong and sustained revenue growth")
    score = diff_similarity(base, inserted)
    assert score is not None
    assert 0.7 < score < 1.0


def test_diff_detects_deletion():
    base = tokenize("the group reported strong and sustained revenue growth")
    deleted = tokenize("the group reported revenue growth")
    score = diff_similarity(base, deleted)
    assert score is not None
    assert 0.5 < score < 1.0


def test_diff_detects_reordering():
    a = tokenize("alpha beta gamma delta epsilon")
    b = tokenize("epsilon delta gamma beta alpha")
    score = diff_similarity(a, b)
    assert score is not None
    assert score < 1.0


def test_diff_unchanged_text_returns_one():
    tokens = tokenize("no changes were made to this paragraph at all")
    assert diff_similarity(tokens, list(tokens)) == 1.0


def test_diff_stable_on_long_documents():
    long_a = tokenize(("paragraph one two three four five. " * 500))
    long_b = tokenize(("paragraph one two three four five. " * 500) + "one extra sentence here.")
    score = diff_similarity(long_a, long_b)
    assert score is not None
    assert score > 0.95


# ---------------------------------------------------------------------------
# Diff runtime policy (diff_similarity_with_mode / token threshold)
# ---------------------------------------------------------------------------


def test_diff_with_mode_short_documents_use_full_no_autojunk():
    tokens_a = tokenize("the group reported strong revenue growth this year")
    tokens_b = tokenize("the group reported weak revenue decline this year")
    result = diff_similarity_with_mode(tokens_a, tokens_b, token_threshold=1000)
    assert result.mode == DiffMode.FULL_NO_AUTOJUNK
    assert result.value is not None
    assert result.value == diff_similarity(tokens_a, tokens_b, autojunk=False)
    assert result.duration_ms is not None
    assert result.duration_ms >= 0.0


def test_diff_with_mode_long_documents_are_skipped_not_fabricated():
    tokens_a = ["word"] * 2000
    tokens_b = ["word"] * 2000
    result = diff_similarity_with_mode(tokens_a, tokens_b, token_threshold=1000)
    assert result.mode == DiffMode.SKIPPED_TOKEN_LIMIT
    assert result.value is None
    assert result.duration_ms is None


def test_diff_with_mode_threshold_boundary_is_inclusive():
    """Exactly at the threshold, the document is NOT over the limit -- only
    strictly greater than `token_threshold` triggers a skip.
    """
    tokens_a = ["word"] * 500
    tokens_b = ["word"] * 500
    at_threshold = diff_similarity_with_mode(tokens_a, tokens_b, token_threshold=500)
    assert at_threshold.mode == DiffMode.FULL_NO_AUTOJUNK

    one_over = diff_similarity_with_mode(tokens_a + ["word"], tokens_b, token_threshold=500)
    assert one_over.mode == DiffMode.SKIPPED_TOKEN_LIMIT
    assert one_over.value is None


def test_diff_with_mode_checks_either_document():
    short_tokens = ["word"] * 10
    long_tokens = ["word"] * 2000
    result = diff_similarity_with_mode(short_tokens, long_tokens, token_threshold=1000)
    assert result.mode == DiffMode.SKIPPED_TOKEN_LIMIT


def test_diff_with_mode_full_autojunk_mode_is_labeled_when_explicitly_requested():
    tokens_a = tokenize("the group reported strong revenue growth this year")
    tokens_b = tokenize("the group reported weak revenue decline this year")
    result = diff_similarity_with_mode(tokens_a, tokens_b, token_threshold=1000, autojunk=True)
    assert result.mode == DiffMode.FULL_AUTOJUNK
    assert result.value is not None


def test_diff_with_mode_deterministic():
    tokens_a = tokenize("the group reported strong revenue growth this year")
    tokens_b = tokenize("the group reported weak revenue decline this year")
    first = diff_similarity_with_mode(tokens_a, tokens_b, token_threshold=1000)
    second = diff_similarity_with_mode(tokens_a, tokens_b, token_threshold=1000)
    assert first.value == second.value
    assert first.mode == second.mode


def test_diff_with_mode_skip_avoids_expensive_computation():
    """A skipped comparison must return near-instantly regardless of size --
    proving the threshold check happens before SequenceMatcher runs, not
    after.
    """
    tokens_a = ["revenue", "growth", "strong"] * 20000
    tokens_b = ["revenue", "decline", "weak"] * 20000
    started = time.monotonic()
    result = diff_similarity_with_mode(tokens_a, tokens_b, token_threshold=1000)
    elapsed = time.monotonic() - started
    assert result.mode == DiffMode.SKIPPED_TOKEN_LIMIT
    assert elapsed < 0.1


def test_diff_with_mode_insertion_removal_reorder_under_threshold():
    base = tokenize("the group reported strong revenue growth this year")
    inserted = tokenize("the group reported strong and sustained revenue growth this year")
    removed = tokenize("the group reported revenue growth this year")
    reordered = tokenize("this year the group reported strong revenue growth")

    for other in (inserted, removed, reordered):
        result = diff_similarity_with_mode(base, other, token_threshold=1000)
        assert result.mode == DiffMode.FULL_NO_AUTOJUNK
        assert result.value is not None
        assert 0.0 <= result.value <= 1.0


def test_diff_with_mode_repeated_boilerplate_under_threshold():
    boilerplate = tokenize("forward-looking statements involve risks and uncertainties. " * 20)
    result = diff_similarity_with_mode(boilerplate, list(boilerplate), token_threshold=10000)
    assert result.mode == DiffMode.FULL_NO_AUTOJUNK
    assert result.value == 1.0


# ---------------------------------------------------------------------------
# Edit similarity (RapidFuzz token-level Levenshtein)
# ---------------------------------------------------------------------------


def test_edit_identical_documents_returns_one():
    tokens = tokenize("the group reported strong revenue growth")
    assert edit_similarity(tokens, tokens) == 1.0


def test_edit_bounded_between_zero_and_one():
    a = tokenize("revenue increased due to strong demand")
    b = tokenize("costs decreased due to efficiency gains")
    score = edit_similarity(a, b)
    assert score is not None
    assert 0.0 <= score <= 1.0


def test_edit_both_empty_returns_none():
    assert edit_similarity([], []) is None


def test_edit_one_side_empty_returns_zero():
    a = tokenize("revenue growth continued")
    assert edit_similarity(a, []) == 0.0


def test_edit_distinguishes_from_diff_on_reordering():
    """Reordering a long run of tokens: SequenceMatcher can match large
    contiguous blocks (finds long common subsequences even out of place in
    some cases), while token-level Levenshtein pays a substitution/shift
    cost per displaced token. The two metrics need not be equal.
    """
    a = tokenize("alpha beta gamma delta epsilon zeta eta theta")
    b = tokenize("theta eta zeta epsilon delta gamma beta alpha")
    diff_score = diff_similarity(a, b)
    edit_score = edit_similarity(a, b)
    assert diff_score is not None and edit_score is not None
    assert diff_score != edit_score


def test_edit_long_document_performance_and_no_pathological_memory():
    """RapidFuzz's bit-parallel implementation should comfortably handle
    realistically sized annual-report token counts (tens of thousands) well
    under a second, with no quadratic blow-up.
    """
    long_a = tokenize("the group reported strong revenue growth this year. " * 4000)
    long_b = tokenize("the group reported weak revenue decline this year. " * 4000)
    assert len(long_a) > 20000

    started = time.monotonic()
    score = edit_similarity(long_a, long_b)
    elapsed = time.monotonic() - started

    assert score is not None
    assert 0.0 <= score <= 1.0
    assert elapsed < 5.0


# ---------------------------------------------------------------------------
# General metric behavior (across all four metrics)
# ---------------------------------------------------------------------------


def _all_metrics(text_a: str, text_b: str):
    tokens_a, tokens_b = tokenize(text_a), tokenize(text_b)
    return {
        "cosine": lexical_cosine_similarity(tokens_a, tokens_b),
        "jaccard": jaccard_similarity(tokens_a, tokens_b),
        "diff": diff_similarity(tokens_a, tokens_b),
        "edit": edit_similarity(tokens_a, tokens_b),
    }


def test_all_metrics_identical_documents():
    text = "the board approved the annual dividend and capital expenditure plan"
    results = _all_metrics(text, text)
    for name, value in results.items():
        assert value == 1.0, f"{name} expected 1.0 for identical docs, got {value}"


def test_all_metrics_completely_different_documents():
    results = _all_metrics(
        "apples bananas cherries dates elderberries", "wolves tigers lions bears eagles"
    )
    for name, value in results.items():
        assert value is not None
        assert value < 0.3, f"{name} expected a low score for disjoint docs, got {value}"


def test_all_metrics_one_empty_document():
    results = _all_metrics("revenue increased significantly this year", "")
    # Cosine similarity of a zero vector is mathematically undefined, so it
    # returns None -- unlike Jaccard/diff/edit, whose "0 overlap against a
    # nonempty side" case is well-defined as 0.0.
    assert results["cosine"] is None
    for name in ("jaccard", "diff", "edit"):
        assert results[name] == 0.0, f"{name} expected 0.0 when one side is empty, got {results[name]}"


def test_all_metrics_both_empty_documents():
    results = _all_metrics("", "")
    for name, value in results.items():
        assert value is None, f"{name} expected None for both-empty docs, got {value}"


def test_all_metrics_case_differences_do_not_matter():
    """Tokenization lowercases before metrics run, so case alone must not
    register as a difference."""
    results = _all_metrics(
        "Revenue Growth Was Strong This Year", "revenue growth was strong this year"
    )
    for name, value in results.items():
        assert value == 1.0, f"{name} expected 1.0 for a case-only difference, got {value}"


def test_all_metrics_punctuation_differences_do_not_matter():
    results = _all_metrics(
        "assets, liabilities, and equity", "assets liabilities and equity"
    )
    for name, value in results.items():
        assert value == 1.0, f"{name} expected 1.0 for a punctuation-only difference, got {value}"


def test_all_metrics_whitespace_differences_do_not_matter():
    results = _all_metrics(
        "the group\nreported   strong\tresults", "the group reported strong results"
    )
    for name, value in results.items():
        assert value == 1.0, f"{name} expected 1.0 for a whitespace-only difference, got {value}"


def test_all_metrics_inserted_paragraph():
    base = "the group reported strong revenue growth this year."
    inserted = base + " a new risk factor relating to currency exposure was also disclosed."
    results = _all_metrics(base, inserted)
    for name, value in results.items():
        assert value is not None
        assert 0.0 < value < 1.0, f"{name} expected a bounded intermediate score, got {value}"


def test_all_metrics_removed_paragraph():
    base = "the group reported strong revenue growth this year. a new risk factor was disclosed."
    removed = "the group reported strong revenue growth this year."
    results = _all_metrics(base, removed)
    for name, value in results.items():
        assert value is not None
        assert 0.0 < value < 1.0, f"{name} expected a bounded intermediate score, got {value}"


def test_all_metrics_reordered_paragraph():
    a = "first paragraph text. second paragraph text. third paragraph text."
    b = "third paragraph text. first paragraph text. second paragraph text."
    results = _all_metrics(a, b)
    # Cosine/Jaccard-on-unigrams-adjacent metrics may still score highly
    # since the words are the same; diff/edit should register the reorder.
    assert results["diff"] is not None and results["diff"] < 1.0
    assert results["edit"] is not None and results["edit"] < 1.0


def test_all_metrics_repeated_boilerplate_scores_highly():
    boilerplate = "forward-looking statements involve risks and uncertainties. " * 20
    results = _all_metrics(boilerplate, boilerplate)
    for name, value in results.items():
        assert value == 1.0, f"{name} expected 1.0 for identical boilerplate, got {value}"


def test_all_metrics_long_synthetic_documents():
    """A long, lexically varied document (not a single repeated phrase --
    see the dedicated low-diversity test below for why that distinction
    matters to Jaccard) with a small addition should score highly across
    every metric.
    """
    sentences = [
        f"paragraph {i} discusses financial performance, liquidity, and risk factors in detail."
        for i in range(1000)
    ]
    long_a = " ".join(sentences)
    long_b = long_a + " an additional closing note was appended at the end."
    results = _all_metrics(long_a, long_b)
    for name, value in results.items():
        assert value is not None
        assert 0.9 < value <= 1.0, f"{name} expected a high score for a small addition, got {value}"


def test_jaccard_sensitive_to_low_bigram_diversity_in_repetitive_text():
    """Known edge case: Jaccard over bigrams has a small "vocabulary" when
    the base document is a single phrase repeated verbatim (e.g. boilerplate
    with almost no variation) -- the unique-bigram SET stays tiny regardless
    of repetition count, so even a short, textually minor addition can
    introduce a large *proportional* number of new unique bigrams and swing
    the score much more than cosine/diff/edit would for the same addition.
    This is expected Jaccard-on-shingles behavior, not a bug, but it means
    Jaccard should be read alongside the other metrics rather than alone
    for highly repetitive boilerplate-heavy sections.
    """
    base = "the group discusses its financial performance in detail. " * 1000
    with_tail = base + "an additional note was added."

    results = _all_metrics(base, with_tail)
    assert results["cosine"] is not None and results["cosine"] > 0.95
    assert results["jaccard"] is not None and results["jaccard"] < 0.7


def test_all_metrics_non_ascii_text():
    results = _all_metrics("Café résumé naïve façade", "Café résumé naïve façade")
    for name, value in results.items():
        assert value == 1.0, f"{name} expected 1.0 for identical non-ASCII docs, got {value}"


def test_all_metrics_numeric_heavy_text():
    a = "revenue was 12,500.50 in 2023 and 13,750.25 in 2024"
    b = "revenue was 12,500.50 in 2023 and 15,000.00 in 2024"
    results = _all_metrics(a, b)
    for name, value in results.items():
        assert value is not None
        assert 0.0 < value < 1.0, f"{name} expected a bounded intermediate score, got {value}"


def test_compute_metrics_returns_metric_set_and_matches_individual_functions():
    metric_set = compute_metrics("revenue increased this year", "revenue decreased this year")
    tokens_a = tokenize("revenue increased this year")
    tokens_b = tokenize("revenue decreased this year")
    assert metric_set.lexical_cosine_similarity == lexical_cosine_similarity(tokens_a, tokens_b)
    assert metric_set.jaccard_similarity == jaccard_similarity(tokens_a, tokens_b)
    assert metric_set.diff_similarity == diff_similarity(tokens_a, tokens_b)
    assert metric_set.edit_similarity == edit_similarity(tokens_a, tokens_b)


def test_compute_metrics_values_excludes_none():
    metric_set = compute_metrics("", "")
    assert metric_set.values() == []


def test_compute_metrics_respects_configured_diff_token_threshold():
    from market_documents.services.similarity_config import SimilarityConfig

    long_text_a = "word " * 2000
    long_text_b = "phrase " * 2000

    tight_config = SimilarityConfig(diff_token_threshold=500)
    metric_set = compute_metrics(long_text_a, long_text_b, tight_config)

    assert metric_set.diff_mode == DiffMode.SKIPPED_TOKEN_LIMIT
    assert metric_set.diff_similarity is None
    # The other three metrics remain fully computed despite the diff skip.
    assert metric_set.lexical_cosine_similarity is not None
    assert metric_set.jaccard_similarity is not None
    assert metric_set.edit_similarity is not None


# ---------------------------------------------------------------------------
# Length-change features
# ---------------------------------------------------------------------------


def test_length_change_features_basic():
    features = compute_length_change_features(
        earlier_word_count=100,
        later_word_count=150,
        earlier_character_count=600,
        later_character_count=900,
    )
    assert features.word_count_change == 50
    assert features.word_count_change_ratio == 0.5
    assert features.character_count_change == 300
    assert math.isclose(features.character_count_change_ratio, 0.5)


def test_length_change_features_zero_earlier_word_count_gives_none_ratio():
    features = compute_length_change_features(
        earlier_word_count=0,
        later_word_count=100,
        earlier_character_count=0,
        later_character_count=600,
    )
    assert features.word_count_change_ratio is None
    assert features.character_count_change_ratio is None
    assert features.word_count_change == 100


def test_length_change_features_negative_change():
    features = compute_length_change_features(
        earlier_word_count=200,
        later_word_count=100,
        earlier_character_count=1200,
        later_character_count=600,
    )
    assert features.word_count_change == -100
    assert features.word_count_change_ratio == -0.5
