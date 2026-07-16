"""Shared, versioned tokenization for lexical similarity metrics.

This is deliberately not a second cleaning pass -- `NarrativeDocument.cleaned_text`
is already the conservatively cleaned, near-lossless representation from
Milestone 2. Everything here is a deterministic *metric-preparation* step:
Unicode-normalization verification, lowercasing, and token-boundary rules.
No summarization, stemming, lemmatization, synonym handling, or stop-word
removal happens anywhere in this module -- literal wording and boilerplate
reuse are exactly what the similarity metrics need to see.

`TOKENIZER_VERSION` is folded into the similarity configuration fingerprint
(see `similarity_config.py`); bump it whenever the regex or pipeline below
changes, so stale tokenization can never silently feed a "skip, identical
run" decision.
"""

import re
import unicodedata

TOKENIZER_VERSION = 1

# Numeric tokens keep internal '.' and ',' so "12,500.50" stays one token.
# Word tokens keep internal apostrophes and hyphens so "shareholders'" and
# "year-end" each stay one token. Every other character (whitespace, other
# punctuation) is a delimiter and is dropped.
_NUMERIC_TOKEN = r"\d+(?:[.,]\d+)*"
# `[^\W\d_]` is "any Unicode letter" (a word character that's neither a
# digit nor underscore) -- plain `[a-z]` would silently drop accented and
# other non-ASCII letters entirely rather than tokenizing them. The
# trailing optional apostrophe catches bare plural possessives
# ("shareholders'", "directors'"), where no letter follows the mark.
_LETTER = r"[^\W\d_]"
_WORD_TOKEN = rf"{_LETTER}+(?:['’\-]{_LETTER}+)*['’]?"
_TOKEN_RE = re.compile(rf"{_NUMERIC_TOKEN}|{_WORD_TOKEN}")


def tokenize(text: str) -> list[str]:
    """Tokenize cleaned narrative text into a deterministic list of unigrams.

    Pipeline (fixed order):
    1. Verify/apply NFKC Unicode normalization (idempotent against the M2
       cleaning pipeline, which already normalizes -- this step makes that
       invariant explicit rather than assumed).
    2. Lowercase.
    3. Extract tokens via a single regex pass distinguishing numeric tokens
       from word tokens (see module docstring).
    4. Drop any empty matches (defensive; the regex cannot produce them).

    Stop words are retained. No stemming or lemmatization is performed.
    """
    normalized = unicodedata.normalize("NFKC", text).lower()
    return [tok for tok in _TOKEN_RE.findall(normalized) if tok]


def bigrams(tokens: list[str], shingle_size: int = 2) -> list[tuple[str, ...]]:
    """Consecutive-token shingles of `shingle_size`, in stable order.

    Used for the Jaccard metric's phrase-overlap representation. Returns an
    empty list when there are fewer than `shingle_size` tokens -- callers
    must handle that explicitly rather than treating it as a zero-overlap
    result.
    """
    if shingle_size < 1 or len(tokens) < shingle_size:
        return []
    return [tuple(tokens[i : i + shingle_size]) for i in range(len(tokens) - shingle_size + 1)]
