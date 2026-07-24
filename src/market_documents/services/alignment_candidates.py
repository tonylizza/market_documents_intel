"""Semantic candidate retrieval: pgvector cosine search restricted to the
immediately earlier report's embeddings.

Candidates are computed transiently here and never persisted as their own
table (per the milestone's default preference) -- only the accepted
alignment ends up in `PassageAlignment`, with `candidate_rank` and
`best_second_margin` capturing enough of the discarded-candidate context for
audit without storing every rejected comparison.

Defaults to exact cosine distance (`<=>`), not the HNSW index added in
Milestone 4's completion: the real corpus produces roughly 200-300 eligible
passages per report side (see `passage_config.py`'s docstring for the
corpus-wide estimate), so a single pair's candidate search is a few hundred
exact comparisons -- already served in single-digit milliseconds by the
existing `embedding_run_id` B-tree, and real-corpus benchmarking
(`retrieval_benchmark.py`) found the HNSW index gives no measurable recall
or latency benefit at this scale/access pattern. `search_mode` exists for
that benchmark and for deterministic testing, not to change this module's
default caller-visible behavior.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from market_documents.models.embedding import PassageEmbedding
from market_documents.models.passage import Passage
from market_documents.services.retrieval_config import RETRIEVAL_CONFIG, VectorSearchMode


@dataclass(frozen=True)
class CandidateMatch:
    passage: Passage
    semantic_similarity: float


def get_semantic_candidates(
    session: Session,
    *,
    later_embedding_vector: list[float],
    earlier_embedding_run_id: uuid.UUID,
    top_k: int,
    min_semantic_similarity: float,
    search_mode: VectorSearchMode = VectorSearchMode.EXACT,
    ef_search: int | None = None,
) -> list[CandidateMatch]:
    """Top-k earlier-report passages by cosine similarity to one later passage.

    Restricted to `earlier_embedding_run_id` (the specific earlier
    EmbeddingRun pinned by the AlignmentRun) and to passages not excluded
    from alignment. Ties in distance are broken deterministically by
    `passage_index`. Candidates below `min_semantic_similarity` are dropped
    -- the caller must never treat an empty result as an error, only as "no
    semantic candidate cleared the bar."

    `search_mode=HNSW` sets pgvector's per-query `hnsw.ef_search` and enables
    `hnsw.iterative_scan` (relaxed_order) via `SET LOCAL` so the approximate
    index can still honor the `embedding_run_id`/`excluded_from_alignment`
    filter -- without it, a filtered HNSW scan can return fewer than
    `top_k` rows even when more exist. Scoped to this transaction only; it
    never changes `search_mode=EXACT` (the production default)'s query or
    plan.
    """
    if search_mode is VectorSearchMode.HNSW:
        effective_ef_search = ef_search if ef_search is not None else RETRIEVAL_CONFIG.hnsw_ef_search
        # SET LOCAL does not accept bind parameters for its value; ef_search
        # is an internally-computed int (config default or caller argument),
        # never raw user input.
        session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        session.execute(text(f"SET LOCAL hnsw.ef_search = {int(effective_ef_search)}"))

    distance = PassageEmbedding.embedding.cosine_distance(later_embedding_vector)
    rows = session.execute(
        select(Passage, distance.label("distance"))
        .join(PassageEmbedding, PassageEmbedding.passage_id == Passage.id)
        .where(
            PassageEmbedding.embedding_run_id == earlier_embedding_run_id,
            Passage.excluded_from_alignment.is_(False),
        )
        .order_by(distance, Passage.passage_index)
        .limit(top_k)
    ).all()

    candidates: list[CandidateMatch] = []
    for passage, dist in rows:
        similarity = 1.0 - float(dist)
        if similarity < min_semantic_similarity:
            continue
        candidates.append(CandidateMatch(passage=passage, semantic_similarity=similarity))
    return candidates
