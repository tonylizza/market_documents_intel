from market_documents.services.financial_language_tokenization import (
    expand_inflections_and_spellings,
    match_phrases_and_unigrams,
    negated_token_positions,
    pluralize,
    spelling_variants,
    tokenize_sentences,
)


# --------------------------------------------------------------------------
# Sentence splitting / base tokenization (Unicode normalization, lowercase,
# punctuation, apostrophes, hyphens all delegate to similarity_tokenization)
# --------------------------------------------------------------------------


def test_sentence_split_stops_at_full_stop():
    sentences = tokenize_sentences("Revenue increased. Risk remained elevated.")
    assert sentences == [["revenue", "increased"], ["risk", "remained", "elevated"]]


def test_case_normalization_is_lowercase():
    sentences = tokenize_sentences("REVENUE Increased")
    assert sentences == [["revenue", "increased"]]


def test_apostrophe_retained_in_token():
    sentences = tokenize_sentences("The shareholders' meeting was held.")
    assert "shareholders'" in sentences[0]


def test_hyphenated_word_stays_one_token():
    sentences = tokenize_sentences("The year-end results were strong.")
    assert "year-end" in sentences[0]


def test_empty_text_yields_no_sentences():
    assert tokenize_sentences("") == []


def test_punctuation_only_yields_no_sentences():
    assert tokenize_sentences("...") == []


# --------------------------------------------------------------------------
# Controlled inflection / spelling-variant expansion (dictionary-import time)
# --------------------------------------------------------------------------


def test_pluralize_sibilant_ending():
    assert pluralize("loss") == "losses"


def test_pluralize_consonant_y_ending():
    assert pluralize("liability") == "liabilities"


def test_pluralize_default_case():
    assert pluralize("risk") == "risks"


def test_pluralize_phrase_returns_none():
    assert pluralize("going concern") is None


def test_spelling_variant_ize_to_ise():
    assert spelling_variants("recognize") == {"recognise"}


def test_spelling_variant_ization_to_isation():
    assert spelling_variants("organization") == {"organisation"}


def test_spelling_variant_yze_to_yse():
    assert spelling_variants("analyze") == {"analyse"}


def test_spelling_variant_none_for_unrelated_word():
    assert spelling_variants("risk") == set()


def test_expand_inflections_and_spellings_combines_both():
    variants = expand_inflections_and_spellings("recognize")
    assert variants == {"recognizes", "recognise"}


def test_expand_inflections_and_spellings_phrase_unexpanded():
    assert expand_inflections_and_spellings("going concern") == set()


def test_expand_inflections_and_spellings_never_includes_original():
    assert "risk" not in expand_inflections_and_spellings("risk")


# --------------------------------------------------------------------------
# Phrase matching: unigram, phrase, phrase precedence, repeated terms,
# hyphen-optional phrase matching
# --------------------------------------------------------------------------


def test_unigram_match():
    tokens = ["revenue", "declined", "sharply"]
    matches = match_phrases_and_unigrams(tokens, {1: {("revenue",), ("declined",)}})
    assert (("revenue",), 0, 1) in matches
    assert (("declined",), 1, 1) in matches


def test_phrase_match_takes_precedence_over_unigrams():
    tokens = ["going", "concern", "basis"]
    term_keys = {2: {("going", "concern")}, 1: {("going",), ("concern",)}}
    matches = match_phrases_and_unigrams(tokens, term_keys)
    assert matches == [(("going", "concern"), 0, 2)]


def test_repeated_term_counted_each_occurrence():
    tokens = ["risk", "risk", "risk"]
    matches = match_phrases_and_unigrams(tokens, {1: {("risk",)}})
    assert len(matches) == 3


def test_hyphen_optional_phrase_match_single_token():
    tokens = ["the", "going-concern", "basis"]
    matches = match_phrases_and_unigrams(tokens, {2: {("going", "concern")}})
    assert matches == [(("going", "concern"), 1, 1)]


def test_no_match_passage_returns_empty():
    tokens = ["ordinary", "narrative", "prose"]
    assert match_phrases_and_unigrams(tokens, {1: {("risk",)}}) == []


def test_longer_phrase_preferred_over_shorter_overlapping_phrase():
    tokens = ["credit", "risk", "management"]
    term_keys = {2: {("credit", "risk")}, 3: {("credit", "risk", "management")}}
    matches = match_phrases_and_unigrams(tokens, term_keys)
    assert matches == [(("credit", "risk", "management"), 0, 3)]


# --------------------------------------------------------------------------
# Negation: conservative window, clause-boundary stop, false negators
# --------------------------------------------------------------------------


def test_negation_marks_following_tokens_within_window():
    tokens = ["the", "outlook", "is", "not", "favourable", "this", "year"]
    negated = negated_token_positions(tokens, window=5)
    assert 4 in negated  # "favourable"


def test_negation_stops_at_boundary_conjunction():
    tokens = ["it", "is", "not", "favourable", "but", "management", "remains", "confident"]
    negated = negated_token_positions(tokens, window=10)
    assert 3 in negated  # "favourable"
    assert 5 not in negated  # "management" -- past the "but" boundary


def test_negation_respects_window_limit():
    tokens = ["not"] + ["word"] * 10
    negated = negated_token_positions(tokens, window=3)
    assert negated == {1, 2, 3}


def test_false_negator_notwithstanding_does_not_trigger_negation():
    tokens = ["revenue", "fell", "notwithstanding", "strong", "demand"]
    assert negated_token_positions(tokens) == set()


def test_no_negator_present_yields_empty_set():
    tokens = ["revenue", "increased", "steadily"]
    assert negated_token_positions(tokens) == set()


def test_multiple_negators_each_scope_independently():
    tokens = ["not", "good", "and", "never", "reliable"]
    negated = negated_token_positions(tokens, window=1)
    assert negated == {1, 4}
