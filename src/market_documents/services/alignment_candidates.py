"""Semantic candidate retrieval: exact pgvector cosine search restricted to
the immediately earlier report's embeddings.

Candidates are computed transiently here and never persisted as their own
table (per the milestone's default preference) -- only the accepted
alignment ends up in `PassageAlignment`, with `candidate_rank` and
`best_second_margin` capturing enough of the discarded-candidate context for
audit without storing every rejected comparison.

Uses exact cosine distance (`<=>`), not an approximate index: the real
corpus produces roughly 200-300 eligible passages per report side (see
`passage_config.py`'s docstring for the corpus-wide estimate), so a single
pair's candidate search is a few hundred exact comparisons -- trivial at
this scale, and an ANN index would trade recall for no measurable benefit.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.embedding import PassageEmbedding
from market_documents.models.passage import Passage


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
) -> list[CandidateMatch]:
    """Top-k earlier-report passages by cosine similarity to one later passage.

    Restricted to `earlier_embedding_run_id` (the specific earlier
    EmbeddingRun pinned by the AlignmentRun) and to passages not excluded
    from alignment. Ties in distance are broken deterministically by
    `passage_index`. Candidates below `min_semantic_similarity` are dropped
    -- the caller must never treat an empty result as an error, only as "no
    semantic candidate cleared the bar."
    """
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
