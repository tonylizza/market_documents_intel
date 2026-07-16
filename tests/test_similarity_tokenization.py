from market_documents.services.similarity_tokenization import bigrams, tokenize


def test_tokenize_is_deterministic():
    text = "Revenue increased by 12% in the current period."
    assert tokenize(text) == tokenize(text)


def test_tokenize_lowercases():
    assert tokenize("Revenue Growth") == ["revenue", "growth"]


def test_tokenize_drops_punctuation_as_delimiter():
    assert tokenize("assets, liabilities; and equity.") == ["assets", "liabilities", "and", "equity"]


def test_tokenize_keeps_hyphenated_words_as_one_token():
    assert tokenize("year-end results") == ["year-end", "results"]


def test_tokenize_keeps_apostrophes_as_one_token():
    assert tokenize("the group's revenue") == ["the", "group's", "revenue"]
    assert tokenize("shareholders’ equity") == ["shareholders’", "equity"]


def test_tokenize_keeps_numeric_tokens_with_internal_punctuation():
    assert tokenize("R12,500.50 was recorded") == ["r", "12,500.50", "was", "recorded"]
    assert tokenize("growth of 2024") == ["growth", "of", "2024"]


def test_tokenize_retains_stop_words():
    tokens = tokenize("the group and its subsidiaries")
    assert "the" in tokens
    assert "and" in tokens
    assert "its" in tokens


def test_tokenize_handles_non_ascii_text():
    tokens = tokenize("Café résumé naïve")
    assert tokens == ["café", "résumé", "naïve"]


def test_tokenize_empty_string_returns_empty_list():
    assert tokenize("") == []


def test_tokenize_whitespace_only_returns_empty_list():
    assert tokenize("   \n\t  ") == []


def test_tokenize_ignores_pdf_line_wrap_whitespace_differences():
    assert tokenize("annual\nreport") == tokenize("annual report")


def test_bigrams_stable_order():
    tokens = ["a", "b", "c", "d"]
    assert bigrams(tokens) == [("a", "b"), ("b", "c"), ("c", "d")]


def test_bigrams_configurable_shingle_size():
    tokens = ["a", "b", "c", "d"]
    assert bigrams(tokens, shingle_size=3) == [("a", "b", "c"), ("b", "c", "d")]


def test_bigrams_too_few_tokens_returns_empty():
    assert bigrams(["a"]) == []
    assert bigrams([]) == []


def test_bigrams_exact_shingle_size_returns_one():
    assert bigrams(["a", "b"], shingle_size=2) == [("a", "b")]
