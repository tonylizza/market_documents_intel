"""Query-text normalization for the embedding service.

Deliberately minimal: whitespace collapsing only, never lowercasing or
stripping punctuation -- the corpus embeddings were computed from raw
passage text with no such normalization (see `services/embedding_config.py`),
so a query embedded under a different normalization policy would not be
comparable via cosine similarity. This function exists mainly so a cache key
and a logged/returned "normalized_text" are stable across incidental
whitespace differences in otherwise-identical queries.
"""

import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_query_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()
