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

Milestone "exact candidate retrieval correctness" finding: the paragraph
above describes the *intended* behavior, but until this fix, `EXACT` mode
did nothing to prevent PostgreSQL's planner from choosing the pre-existing
HNSW index (`ix_passage_embeddings_embedding_hnsw_cosine`) for the
`ORDER BY embedding <=> :vec LIMIT :top_k` query shape below -- the SQL is
identical whether or not the caller "intends" an exact scan, and the
planner has no way to know intent from query shape alone. Confirmed via
`EXPLAIN (ANALYZE, BUFFERS)` on the real corpus: for a highly selective
`embedding_run_id` filter (applied *after* the HNSW index's approximate
graph walk, not before it), the planner chose the HNSW index and returned
as few as 4 of the requested 5 rows from an eligible population of 1,055,
silently dropping the true nearest neighbor (see
`docs/exact-candidate-retrieval-correctness.md`). `EXACT` mode now issues
`SET LOCAL enable_indexscan = off` / `enable_bitmapscan = off` for exactly
this reason -- see the docstring below. This guard and the canonical-
embedding query it protects are frozen as of Milestone 6 (see below) --
never modified, only extended alongside.

Milestone 6 ("oversized passage retrieval subchunks") addition: a passage
whose full text exceeds the embedding model's token limit has no canonical
`PassageEmbedding` row (see `passage_embedding.py`), so the query above can
never surface it, no matter how the planner behaves. `get_semantic_candidates`
now also queries `PassageRetrievalChunk` -- an oversized passage's
sentence-bounded, token-safe embedding-time chunks -- for the same
`earlier_embedding_run_id`, using an identical `SET LOCAL
enable_indexscan/enable_bitmapscan = off` guard (a new, separate guard for
the new table, not a change to the canonical query's own guard above, so
the frozen behavior above is untouched). Multiple chunks from the same
passage are aggregated by maximum cosine similarity (minimum distance)
before ranking, per `docs/embedding-eligibility-token-limit-diagnostic.md`
Section 12: "does any part of this passage plausibly correspond," not an
average. See `CandidateMatch.candidate_source` for why this is a distinct,
documented quantity from a canonical passage's own cosine similarity.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from market_documents.models.embedding import PassageEmbedding, PassageRetrievalChunk
from market_documents.models.passage import Passage
from market_documents.services.retrieval_config import RETRIEVAL_CONFIG, VectorSearchMode

CandidateSource = Literal["canonical_embedding", "retrieval_chunk_max"]


@dataclass(frozen=True)
class CandidateMatch:
    passage: Passage
    # For `candidate_source="canonical_embedding"`, a true full-passage
    # cosine similarity -- the only kind of candidate that existed before
    # Milestone 6. For `candidate_source="retrieval_chunk_max"`, this is
    # instead the *maximum* cosine similarity across the passage's retrieval
    # subchunks -- a different, documented quantity (see module docstring)
    # used because the passage itself was never embedded canonically. Never
    # silently conflate the two: a consumer that needs to know which is
    # which must check `candidate_source`.
    semantic_similarity: float
    candidate_source: CandidateSource = "canonical_embedding"


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
    `top_k` rows even when more exist.

    `search_mode=EXACT` (the production default) sets `SET LOCAL
    enable_indexscan = off` and `enable_bitmapscan = off` for the same
    reason: without an explicit planner guard, PostgreSQL is free to select
    the same pre-existing HNSW index for this query's exact shape (`ORDER
    BY <=> LIMIT`) whenever it estimates that plan as cheaper -- there is
    nothing in the query text itself that distinguishes "exact" intent from
    "approximate" intent. Verified via `EXPLAIN` that, without this guard,
    a selective `embedding_run_id` filter can cause the HNSW path to return
    far fewer than `top_k` rows even when the eligible population is
    1,000+, silently dropping the true nearest neighbor (see
    `docs/exact-candidate-retrieval-correctness.md`). Both guards are
    `SET LOCAL`, so they revert automatically at the end of the current
    transaction/savepoint and never leak to another pooled connection's
    later transaction or to a concurrently-open `HNSW`-mode call on a
    different connection.
    """
    if search_mode is VectorSearchMode.HNSW:
        effective_ef_search = ef_search if ef_search is not None else RETRIEVAL_CONFIG.hnsw_ef_search
        # SET LOCAL does not accept bind parameters for its value; ef_search
        # is an internally-computed int (config default or caller argument),
        # never raw user input.
        session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        session.execute(text(f"SET LOCAL hnsw.ef_search = {int(effective_ef_search)}"))
    else:
        # Forces a true sequential scan for this query only. Bounded to the
        # current transaction by SET LOCAL semantics -- see docstring above.
        session.execute(text("SET LOCAL enable_indexscan = off"))
        session.execute(text("SET LOCAL enable_bitmapscan = off"))

    # Frozen (Milestone "exact candidate retrieval correctness"): this query
    # and the planner guard above it must never change.
    distance = PassageEmbedding.embedding.cosine_distance(later_embedding_vector)
    canonical_rows = session.execute(
        select(Passage, distance.label("distance"))
        .join(PassageEmbedding, PassageEmbedding.passage_id == Passage.id)
        .where(
            PassageEmbedding.embedding_run_id == earlier_embedding_run_id,
            Passage.excluded_from_alignment.is_(False),
        )
        .order_by(distance, Passage.passage_index)
        .limit(top_k)
    ).all()

    # Milestone 6 addition: an oversized passage has no row in the query
    # above (see module docstring) but may have retrieval subchunks. The
    # `SET LOCAL enable_indexscan/enable_bitmapscan = off` guard set above
    # (for EXACT mode) is transaction-scoped, not query-scoped, so it
    # already covers this second query too -- no separate guard call is
    # needed, and none is added, to avoid duplicating the frozen guard logic.
    min_chunk_distance = func.min(PassageRetrievalChunk.embedding.cosine_distance(later_embedding_vector)).label(
        "min_distance"
    )
    chunk_rows = session.execute(
        select(Passage, min_chunk_distance)
        .join(PassageRetrievalChunk, PassageRetrievalChunk.passage_id == Passage.id)
        .where(
            PassageRetrievalChunk.embedding_run_id == earlier_embedding_run_id,
            Passage.excluded_from_alignment.is_(False),
        )
        .group_by(Passage.id)
        .order_by(min_chunk_distance, Passage.passage_index)
        .limit(top_k)
    ).all()

    # Merge + dedupe by passage_id (a passage has either a canonical
    # embedding or retrieval chunks, never both, by construction -- see
    # `passage_embedding._run_embedding` -- but dedup defensively keeps the
    # higher-similarity source regardless).
    best_by_passage: dict[uuid.UUID, CandidateMatch] = {}
    for passage, dist in canonical_rows:
        best_by_passage[passage.id] = CandidateMatch(
            passage=passage, semantic_similarity=1.0 - float(dist), candidate_source="canonical_embedding"
        )
    for passage, dist in chunk_rows:
        similarity = 1.0 - float(dist)
        existing = best_by_passage.get(passage.id)
        if existing is None or similarity > existing.semantic_similarity:
            best_by_passage[passage.id] = CandidateMatch(
                passage=passage, semantic_similarity=similarity, candidate_source="retrieval_chunk_max"
            )

    candidates = [c for c in best_by_passage.values() if c.semantic_similarity >= min_semantic_similarity]
    candidates.sort(key=lambda c: (-c.semantic_similarity, c.passage.passage_index))
    return candidates[:top_k]
