"""Deterministic exact-vs-HNSW retrieval benchmark.

Mirrors `alignment_candidates.py`'s query shape exactly (same join, same
exclusion filter, same tie-break) so the benchmark measures the retrieval
pattern this codebase actually uses, not an idealized one. Query passages
are drawn deterministically (ordered by `embedding_run_id`, `passage_index`)
from the real corpus already loaded via `passage_embeddings` -- no random
sampling, so re-running against an unchanged corpus reproduces identical
results.

Each query passage's own embedding is used as the query vector, searched
(report-restricted, matching production) against its own `embedding_run_id`
-- its true nearest neighbor is therefore itself (distance 0), giving a
verifiable ground truth without needing hand-labeled relevance judgments.
"""

import statistics
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from market_documents.models.embedding import PassageEmbedding
from market_documents.models.passage import Passage
from market_documents.services.retrieval_config import MINIMUM_INDEXED_RECALL_AT_10, RETRIEVAL_CONFIG, VectorSearchMode

VECTOR_INDEX_NAME = "ix_passage_embeddings_embedding_hnsw_cosine"

_RESTRICTED_SQL = """
    SELECT pe.passage_id
    FROM passage_embeddings pe
    JOIN passages p ON p.id = pe.passage_id
    WHERE pe.embedding_run_id = :run_id AND p.excluded_from_alignment = false
    ORDER BY pe.embedding <=> CAST(:vec AS vector), p.passage_index
    LIMIT :limit
"""

_UNFILTERED_SQL = """
    SELECT pe.passage_id
    FROM passage_embeddings pe
    ORDER BY pe.embedding <=> CAST(:vec AS vector)
    LIMIT :limit
"""


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _apply_search_mode(session: Session, search_mode: VectorSearchMode, ef_search: int) -> None:
    if search_mode is VectorSearchMode.HNSW:
        # relaxed_order lets the HNSW index honor the embedding_run_id/
        # excluded_from_alignment filter via iterative scanning instead of
        # returning fewer than `limit` rows when the filter is selective.
        # SET LOCAL does not accept bind parameters for its value (it is not
        # a regular statement); ef_search is an internally-computed int
        # (config default or benchmark argument), never raw user input.
        session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        session.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))


def _ranked_ids_restricted(
    session: Session,
    *,
    embedding_run_id: uuid.UUID,
    vector: list[float],
    limit: int,
    search_mode: VectorSearchMode,
    ef_search: int,
) -> tuple[list[uuid.UUID], float]:
    _apply_search_mode(session, search_mode, ef_search)
    start = time.perf_counter()
    rows = session.execute(
        text(_RESTRICTED_SQL),
        {"run_id": str(embedding_run_id), "vec": _vector_literal(vector), "limit": limit},
    ).all()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return [row[0] for row in rows], elapsed_ms


def _ranked_ids_unfiltered(
    session: Session, *, vector: list[float], limit: int, search_mode: VectorSearchMode, ef_search: int
) -> tuple[list[uuid.UUID], float]:
    _apply_search_mode(session, search_mode, ef_search)
    start = time.perf_counter()
    rows = session.execute(text(_UNFILTERED_SQL), {"vec": _vector_literal(vector), "limit": limit}).all()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return [row[0] for row in rows], elapsed_ms


def _explain(session: Session, sql: str, params: dict, search_mode: VectorSearchMode, ef_search: int) -> str:
    _apply_search_mode(session, search_mode, ef_search)
    rows = session.execute(text(f"EXPLAIN ANALYZE {sql}"), params).all()
    return "\n".join(row[0] for row in rows)


@dataclass(frozen=True)
class BenchmarkQuery:
    query_passage_id: uuid.UUID
    embedding_run_id: uuid.UUID
    vector: list[float]


def select_deterministic_benchmark_queries(session: Session, *, queries_per_run: int = 3) -> list[BenchmarkQuery]:
    """Up to `queries_per_run` eligible passages per embedding run, ordered
    deterministically by (embedding_run_id, passage_index) -- no random
    sampling, so results are reproducible across re-runs of an unchanged
    corpus."""
    rows = session.execute(
        select(PassageEmbedding.passage_id, PassageEmbedding.embedding_run_id, PassageEmbedding.embedding)
        .join(Passage, Passage.id == PassageEmbedding.passage_id)
        .where(Passage.excluded_from_alignment.is_(False))
        .order_by(PassageEmbedding.embedding_run_id, Passage.passage_index, PassageEmbedding.passage_id)
    ).all()

    queries: list[BenchmarkQuery] = []
    counts: dict[uuid.UUID, int] = {}
    for passage_id, run_id, vector in rows:
        n = counts.get(run_id, 0)
        if n >= queries_per_run:
            continue
        queries.append(
            BenchmarkQuery(query_passage_id=passage_id, embedding_run_id=run_id, vector=[float(x) for x in vector])
        )
        counts[run_id] = n + 1
    return queries


@dataclass(frozen=True)
class QueryComparison:
    query_passage_id: uuid.UUID
    embedding_run_id: uuid.UUID
    exact_ids: list[uuid.UUID]
    indexed_ids: list[uuid.UUID]
    exact_latency_ms: float
    indexed_latency_ms: float

    def recall_at(self, k: int) -> float:
        exact_set = set(self.exact_ids[:k])
        if not exact_set:
            return 1.0
        indexed_set = set(self.indexed_ids[:k])
        return len(exact_set & indexed_set) / len(exact_set)

    @property
    def top1_match(self) -> bool:
        return bool(self.exact_ids) and bool(self.indexed_ids) and self.exact_ids[0] == self.indexed_ids[0]

    @property
    def rank_overlap(self) -> float:
        n = min(len(self.exact_ids), len(self.indexed_ids))
        if n == 0:
            return 1.0
        matches = sum(1 for i in range(n) if self.exact_ids[i] == self.indexed_ids[i])
        return matches / n


@dataclass(frozen=True)
class RetrievalBenchmarkResult:
    query_count: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mean_rank_overlap: float
    mean_exact_latency_ms: float
    mean_indexed_latency_ms: float
    restricted_plan_exact: str
    restricted_plan_indexed: str
    unfiltered_plan_exact: str
    unfiltered_plan_indexed: str
    unfiltered_indexed_plan_uses_vector_index: bool
    restricted_indexed_plan_uses_vector_index: bool
    fewer_than_k_query_count: int
    meets_minimum_recall_at_10: bool


def run_retrieval_benchmark(
    session: Session,
    *,
    queries_per_run: int = 3,
    top_k: int = 10,
    ef_search: int | None = None,
) -> RetrievalBenchmarkResult:
    """Compare exact vs. HNSW-indexed retrieval on the real (or fixture)
    corpus currently loaded in `session`. Raises ValueError if there are no
    eligible passage embeddings to benchmark against."""
    effective_ef_search = ef_search if ef_search is not None else RETRIEVAL_CONFIG.hnsw_ef_search
    queries = select_deterministic_benchmark_queries(session, queries_per_run=queries_per_run)
    if not queries:
        raise ValueError("no eligible passage embeddings available to benchmark")

    comparisons: list[QueryComparison] = []
    fewer_than_k = 0
    for q in queries:
        exact_ids, exact_ms = _ranked_ids_restricted(
            session, embedding_run_id=q.embedding_run_id, vector=q.vector, limit=top_k,
            search_mode=VectorSearchMode.EXACT, ef_search=effective_ef_search,
        )
        indexed_ids, indexed_ms = _ranked_ids_restricted(
            session, embedding_run_id=q.embedding_run_id, vector=q.vector, limit=top_k,
            search_mode=VectorSearchMode.HNSW, ef_search=effective_ef_search,
        )
        if len(exact_ids) < top_k:
            fewer_than_k += 1
        comparisons.append(
            QueryComparison(
                query_passage_id=q.query_passage_id, embedding_run_id=q.embedding_run_id,
                exact_ids=exact_ids, indexed_ids=indexed_ids,
                exact_latency_ms=exact_ms, indexed_latency_ms=indexed_ms,
            )
        )

    recall_at_1 = statistics.fmean(c.recall_at(1) for c in comparisons)
    recall_at_5 = statistics.fmean(c.recall_at(5) for c in comparisons)
    recall_at_10 = statistics.fmean(c.recall_at(10) for c in comparisons)
    mean_rank_overlap = statistics.fmean(c.rank_overlap for c in comparisons)
    mean_exact_latency_ms = statistics.fmean(c.exact_latency_ms for c in comparisons)
    mean_indexed_latency_ms = statistics.fmean(c.indexed_latency_ms for c in comparisons)

    sample = queries[0]
    restricted_plan_exact = _explain(
        session, _RESTRICTED_SQL, {"run_id": str(sample.embedding_run_id), "vec": _vector_literal(sample.vector), "limit": top_k},
        VectorSearchMode.EXACT, effective_ef_search,
    )
    restricted_plan_indexed = _explain(
        session, _RESTRICTED_SQL, {"run_id": str(sample.embedding_run_id), "vec": _vector_literal(sample.vector), "limit": top_k},
        VectorSearchMode.HNSW, effective_ef_search,
    )
    unfiltered_plan_exact = _explain(
        session, _UNFILTERED_SQL, {"vec": _vector_literal(sample.vector), "limit": top_k},
        VectorSearchMode.EXACT, effective_ef_search,
    )
    unfiltered_plan_indexed = _explain(
        session, _UNFILTERED_SQL, {"vec": _vector_literal(sample.vector), "limit": top_k},
        VectorSearchMode.HNSW, effective_ef_search,
    )

    return RetrievalBenchmarkResult(
        query_count=len(comparisons),
        recall_at_1=recall_at_1,
        recall_at_5=recall_at_5,
        recall_at_10=recall_at_10,
        mean_rank_overlap=mean_rank_overlap,
        mean_exact_latency_ms=mean_exact_latency_ms,
        mean_indexed_latency_ms=mean_indexed_latency_ms,
        restricted_plan_exact=restricted_plan_exact,
        restricted_plan_indexed=restricted_plan_indexed,
        unfiltered_plan_exact=unfiltered_plan_exact,
        unfiltered_plan_indexed=unfiltered_plan_indexed,
        unfiltered_indexed_plan_uses_vector_index=VECTOR_INDEX_NAME in unfiltered_plan_indexed,
        restricted_indexed_plan_uses_vector_index=VECTOR_INDEX_NAME in restricted_plan_indexed,
        fewer_than_k_query_count=fewer_than_k,
        meets_minimum_recall_at_10=recall_at_10 >= MINIMUM_INDEXED_RECALL_AT_10,
    )
