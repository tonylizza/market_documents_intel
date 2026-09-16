"""Pure lexical-change metrics for one `LEXICAL_ONLY` aligned semantic-unit
pair (Track 7C.3, docs/7c3-analytical-eligibility-and-lexical-comparison.md).

Reuses the exact metric functions validated for document-level comparison
in `services.similarity_metrics`/`services.similarity_tokenization` --
no new metric math, no composite score, no threshold, no materiality
label. Every function here takes plain strings and returns plain values,
so it can be unit tested without PostgreSQL, mirroring
`similarity_metrics`'s own convention.
"""

from dataclasses import dataclass

from market_documents.services.similarity_metrics import (
    diff_similarity,
    edit_similarity,
    jaccard_similarity,
    lexical_cosine_similarity,
)
from market_documents.services.similarity_tokenization import tokenize


@dataclass(frozen=True)
class LexicalMetrics:
    lexical_cosine_similarity: float | None
    unigram_jaccard: float | None
    bigram_jaccard: float | None
    edit_similarity: float | None
    sequence_similarity: float | None
    earlier_word_count: int
    later_word_count: int
    word_count_change: int
    word_count_change_pct: float | None


def compute_lexical_metrics(earlier_text: str, later_text: str) -> LexicalMetrics:
    """Tokenize both unit texts once (the same tokenizer used for
    document-level similarity) and compute every 7C.3 lexical metric from
    that shared token list.

    Word counts are token counts from this tokenizer, not
    `SemanticUnit.word_count` (a 7C.1 extraction-provenance field computed
    independently) -- keeping word count and the similarity metrics
    sourced from the same tokenization avoids a spurious mismatch between
    "word count changed by X" and "cosine computed over Y tokens".
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
        lexical_cosine_similarity=lexical_cosine_similarity(tokens_a, tokens_b),
        unigram_jaccard=jaccard_similarity(tokens_a, tokens_b, shingle_size=1),
        bigram_jaccard=jaccard_similarity(tokens_a, tokens_b, shingle_size=2),
        edit_similarity=edit_similarity(tokens_a, tokens_b),
        sequence_similarity=diff_similarity(tokens_a, tokens_b),
        earlier_word_count=earlier_word_count,
        later_word_count=later_word_count,
        word_count_change=word_count_change,
        word_count_change_pct=word_count_change_pct,
    )
