"""Pure lexical-change metrics for one `LEXICAL_ONLY` aligned semantic-unit
pair (Track 7C.3, docs/7c3-analytical-eligibility-and-lexical-comparison.md).

Reuses metric functions from `services.similarity_metrics` chosen
specifically to match the validated research's own metric definitions
(docs/experiments/annual-report-lexical-change-pilot.md Section 5) --
`pairwise_tfidf_cosine_similarity` for `tfidf_cosine` (genuine TF-IDF, not
the document-pipeline's sublinear-TF `lexical_cosine_similarity`) and
`character_edit_similarity` for `edit_similarity` (character-level, not
the document-pipeline's token-level `edit_similarity`). No new metric
math is written here -- every value comes from an existing,
independently-tested `similarity_metrics` function; no composite score,
no threshold, no materiality label.
"""

from dataclasses import dataclass

from market_documents.services.similarity_metrics import (
    character_edit_similarity,
    diff_similarity,
    jaccard_similarity,
    pairwise_tfidf_cosine_similarity,
)
from market_documents.services.similarity_tokenization import tokenize


@dataclass(frozen=True)
class LexicalMetrics:
    tfidf_cosine: float | None
    unigram_jaccard: float | None
    bigram_jaccard: float | None
    edit_similarity: float | None
    sequence_similarity: float | None
    earlier_word_count: int
    later_word_count: int
    word_count_change: int
    word_count_change_pct: float | None


def compute_lexical_metrics(earlier_text: str, later_text: str) -> LexicalMetrics:
    """Compute every 7C.3 lexical metric for one aligned unit's earlier/later
    text.

    `tfidf_cosine`, `unigram_jaccard`, `bigram_jaccard`, and
    `sequence_similarity` are token-based (the shared tokenizer used
    throughout `services.similarity_metrics`); `edit_similarity` is
    character-based, per the research's own definition -- see
    `character_edit_similarity`'s docstring. Word counts are token counts
    from the same shared tokenizer, not `SemanticUnit.word_count` (a 7C.1
    extraction-provenance field computed independently), so word count and
    the token-based metrics are always sourced from one consistent
    tokenization.
    """
    tokens_a = tokenize(earlier_text)
    tokens_b = tokenize(later_text)
    earlier_word_count = len(tokens_a)
    later_word_count = len(tokens_b)
    word_count_change = later_word_count - earlier_word_count
    word_count_change_pct = (
        (word_count_change / earlier_word_count) * 100.0 if earlier_word_count else None
    )

    return LexicalMetrics(
        tfidf_cosine=pairwise_tfidf_cosine_similarity(tokens_a, tokens_b),
        unigram_jaccard=jaccard_similarity(tokens_a, tokens_b, shingle_size=1),
        bigram_jaccard=jaccard_similarity(tokens_a, tokens_b, shingle_size=2),
        edit_similarity=character_edit_similarity(earlier_text, later_text),
        sequence_similarity=diff_similarity(tokens_a, tokens_b),
        earlier_word_count=earlier_word_count,
        later_word_count=later_word_count,
        word_count_change=word_count_change,
        word_count_change_pct=word_count_change_pct,
    )
