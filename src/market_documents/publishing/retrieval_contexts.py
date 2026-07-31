"""Pure, database-free helpers for Milestone 7B.1 embedding/retrieval-context
publishing: text hashing, vector norm, and category deduplication. Mirrors
`labels.py`'s "no function here ever opens a session" rule -- the ORM
field-by-field mapping itself still lives in `publisher.py`, consistent with
that module's existing convention for `Passage`/`PassageComparison`.

Embedding-text-hash caveat: the research side has no equivalent hash on
`PassageEmbedding` (see `services/passage_embedding.py`) -- there was never a
need for one, since "current" embedding selection is governed entirely by
`EmbeddingRun.configuration_hash` plus segmentation-run identity. This
module's hash is therefore a forward-looking drift detector only: it lets a
future publication notice that `app.passages.text` no longer matches what an
already-published vector was computed from, but it cannot be cross-checked
against anything recorded at research-embedding time.
"""

import hashlib
import math
from dataclasses import dataclass


def embedding_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def vector_norm(vector: list[float]) -> float:
    return math.sqrt(sum(component * component for component in vector))


def vector_norm_nonzero(vector: list[float], epsilon: float = 1e-9) -> bool:
    """Mirrors the research side's `embedding_integrity.check_embedding_
    integrity`: dimension/NaN/Infinity are already rejected by the `vector`
    column type at insert time, so a zero vector (undefined cosine
    distance) is the one degenerate case worth checking for explicitly."""
    return vector_norm(vector) > epsilon


@dataclass(frozen=True)
class LanguageSignalTag:
    """One (category, subcategory, adjusted_count) observation for a single
    passage/comparison/side -- the minimal shape `distinct_categories`/
    `distinct_risk_subcategories` need, decoupled from the full app
    `PassageLanguageSignal` ORM row so these functions stay pure."""

    category: str
    subcategory: str | None
    adjusted_count: int


def distinct_categories(tags: list[LanguageSignalTag]) -> list[str]:
    """Distinct categories with at least one non-zero adjusted hit count,
    in first-seen order (deterministic given a deterministically-ordered
    input, which callers already provide via `CORE_CATEGORIES` iteration
    order followed by hit-row iteration order)."""
    seen: dict[str, None] = {}
    for tag in tags:
        if tag.adjusted_count > 0:
            seen.setdefault(tag.category, None)
    return list(seen.keys())


def distinct_risk_subcategories(tags: list[LanguageSignalTag]) -> list[str]:
    seen: dict[str, None] = {}
    for tag in tags:
        if tag.category == "risk" and tag.subcategory is not None and tag.adjusted_count > 0:
            seen.setdefault(tag.subcategory, None)
    return list(seen.keys())
