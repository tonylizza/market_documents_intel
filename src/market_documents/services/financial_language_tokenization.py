"""Deterministic tokenization, term-inflection/spelling-variant expansion,
phrase matching, and negation scoping for Milestone 6 financial-language
signals.

Reuses `similarity_tokenization.tokenize` as the base pass (NFKC normalize,
lowercase, numeric-vs-word token regex) -- no second cleaning pipeline, no
stemming or lemmatization. Everything here is additional, explicitly scoped
machinery on top of that base tokenizer:

- sentence splitting, so negation and clause-boundary scope never leaks
  across a full stop (the base tokenizer discards punctuation entirely, so
  sentence boundaries must be found in the raw text first);
- controlled inflection and UK/South African spelling-variant expansion,
  applied once at dictionary-import time to generate additional term rows
  (never a runtime stemmer);
- longest-phrase-first matching with a narrow hyphen-optional rule (a
  phrase written either as "going concern" or "going-concern" matches once,
  never both);
- a conservative negation window that also treats a small set of clause-
  boundary conjunctions as a scope stop, in addition to sentence punctuation.
"""

import re
from dataclasses import dataclass

from market_documents.services.similarity_tokenization import tokenize

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")

# Regular English pluralization only (spec: "avoid aggressive stemming").
# Applied to single alphabetic words at dictionary-import time -- never to
# phrases, never at match time.
_SIBILANT_ENDING_RE = re.compile(r"(s|x|z|ch|sh)$")
_CONSONANT_Y_ENDING_RE = re.compile(r"[^aeiou]y$")

# UK/South African spelling variants: deliberately limited to the two
# suffix families where a blind suffix swap is safe and essentially
# exception-free (-ize/-ization -> -ise/-isation, -yze -> -yse). Broader
# families (-or/-our, -er/-re) have too many false-positive exceptions
# ("sensor", "actor", "creditor") for a blind suffix rule to be defensible,
# so they are intentionally not attempted here.
_IZE_SUFFIX_RE = re.compile(r"(ize|ization)$")
_YZE_SUFFIX_RE = re.compile(r"yze$")

DEFAULT_NEGATORS = frozenset({"not", "no", "never", "neither", "without", "unlikely"})
DEFAULT_BOUNDARY_CONJUNCTIONS = frozenset({"but", "however", "although", "though", "yet"})


def split_sentences(text: str) -> list[str]:
    """Split on `.`/`!`/`?` runs, dropping empty segments. This is the
    boundary negation and phrase matching both respect -- neither ever
    crosses from one sentence into the next."""
    return [s for s in (seg.strip() for seg in _SENTENCE_SPLIT_RE.split(text)) if s]


def tokenize_sentences(text: str) -> list[list[str]]:
    """Per-sentence tokenized text, using the shared base tokenizer for each
    sentence independently."""
    return [tokenize(sentence) for sentence in split_sentences(text)]


def pluralize(word: str) -> str | None:
    """The regular English plural of `word`, or `None` if `word` is not a
    plain alphabetic single word (phrases and non-alphabetic terms are never
    inflected here)."""
    if not word.isalpha():
        return None
    if _SIBILANT_ENDING_RE.search(word):
        return word + "es"
    if _CONSONANT_Y_ENDING_RE.search(word):
        return word[:-1] + "ies"
    return word + "s"


def spelling_variants(word: str) -> set[str]:
    """UK/South African spelling variant(s) of a US-spelled `word`, or an
    empty set if none of the two safe suffix rules apply."""
    if not word.isalpha():
        return set()
    variants: set[str] = set()
    if _IZE_SUFFIX_RE.search(word):
        variants.add(_IZE_SUFFIX_RE.sub(lambda m: "ise" if m.group(1) == "ize" else "isation", word))
    elif _YZE_SUFFIX_RE.search(word):
        variants.add(_YZE_SUFFIX_RE.sub("yse", word))
    return variants


def expand_inflections_and_spellings(normalized_term: str) -> set[str]:
    """All controlled-inflection and spelling-variant forms of a single-word
    normalized term, not including the original form itself. Phrases (any
    term containing whitespace) are returned unexpanded -- this milestone
    does not inflect multi-word terms."""
    if " " in normalized_term:
        return set()
    variants: set[str] = set()
    plural = pluralize(normalized_term)
    if plural is not None:
        variants.add(plural)
    variants |= spelling_variants(normalized_term)
    for variant in list(variants):
        variants |= spelling_variants(variant)
    variants.discard(normalized_term)
    return variants


@dataclass(frozen=True)
class PhraseMatch:
    term_key: tuple[str, ...]
    sentence_index: int
    start_token: int
    token_span: int
    negated: bool


def _hyphen_split_key(token: str) -> tuple[str, ...] | None:
    if "-" not in token:
        return None
    parts = tuple(p for p in token.split("-") if p)
    return parts if len(parts) > 1 else None


def match_phrases_and_unigrams(
    tokens: list[str], term_keys_by_length: dict[int, set[tuple[str, ...]]]
) -> list[tuple[tuple[str, ...], int, int]]:
    """Greedy, longest-phrase-first, left-to-right scan over one sentence's
    tokens. Returns `(term_key, start_token, token_span)` for every match;
    tokens consumed by an accepted phrase match are never also reported as
    a component unigram match (phrase precedence, no double-counting).

    A single token containing an internal hyphen (e.g. "going-concern") is
    additionally checked against its hyphen-split form, so a phrase written
    either as "going concern" or "going-concern" matches exactly once,
    whichever form the passage happens to use.
    """
    if not term_keys_by_length:
        return []
    max_len = max(term_keys_by_length)
    matches: list[tuple[tuple[str, ...], int, int]] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        for length in range(min(max_len, n - i), 0, -1):
            candidate = tuple(tokens[i : i + length])
            if candidate in term_keys_by_length.get(length, ()):
                matches.append((candidate, i, length))
                i += length
                matched = True
                break
        if matched:
            continue
        hyphen_key = _hyphen_split_key(tokens[i])
        if hyphen_key is not None and hyphen_key in term_keys_by_length.get(len(hyphen_key), ()):
            matches.append((hyphen_key, i, 1))
            i += 1
            continue
        i += 1
    return matches


def negated_token_positions(
    tokens: list[str],
    *,
    negators: frozenset[str] = DEFAULT_NEGATORS,
    boundary_conjunctions: frozenset[str] = DEFAULT_BOUNDARY_CONJUNCTIONS,
    window: int = 5,
) -> set[int]:
    """Token indices within this sentence's negation scope.

    Exact-token matching only (never substring/prefix), so a token like
    "notwithstanding" -- a false negator -- never triggers negation just
    because it contains "not". Scope from a negator at position `i` extends
    to `min(i + window, next boundary conjunction position - 1)`; sentence
    boundaries are handled by the caller never passing tokens across a
    sentence (see `tokenize_sentences`).
    """
    negated: set[int] = set()
    for i, token in enumerate(tokens):
        if token not in negators:
            continue
        end = min(i + window, len(tokens) - 1)
        for j in range(i + 1, end + 1):
            if tokens[j] in boundary_conjunctions:
                break
            negated.add(j)
    return negated
