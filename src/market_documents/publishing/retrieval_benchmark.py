"""Milestone 7B.1: exact-vs-HNSW retrieval benchmark for the application
database.

Mirrors `services/retrieval_benchmark.py`'s self-recall design (a query
passage's own vector is searched for; its true nearest neighbor is itself,
giving a verifiable ground truth without hand-labeled relevance judgments)
but against `app.passage_embeddings` for one publication, unfiltered across
the *entire* active corpus -- unlike the research benchmark, which is always
scoped to one `embedding_run_id` (one report side), application-layer
semantic search searches the whole publication at once, so that is the
access pattern this benchmark must measure.
"""

import statistics
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from market_documents.publishing.models import PassageEmbedding as AppPassageEmbedding

VECTOR_INDEX_NAME = "ix_app_passage_embeddings_hnsw_cosine"

# Mirrors the research side's `MINIMUM_INDEXED_RECALL_AT_10` bar (see
# `services/retrieval_config.py`) -- kept as an independent constant here
# since the app-side corpus scale/access pattern (whole-publication search)
# differs from the research per-report-pair candidate search.
MINIMUM_INDEXED_RECALL_AT_10 = 0.95

_UNFILTERED_SQL = """
    SELECT passage_id
    FROM app.passage_embeddings
    WHERE publication_id = :publication_id
    ORDER BY embedding <=> CAST(:vec AS vector)
    LIMIT :limit
"""

_COMPANY_FILTERED_SQL = """
    SELECT pe.passage_id
    FROM app.passage_embeddings pe
    JOIN app.passages p ON p.id = pe.passage_id
    WHERE pe.publication_id = :publication_id AND p.company_id = :company_id
    ORDER BY pe.embedding <=> CAST(:vec AS vector)
    LIMIT :limit
"""


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def _set_search_mode(session: Session, mode: str, ef_search: int) -> None:
    if mode == "hnsw":
        session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        session.execute(text(f"SET LOCAL hnsw.ef_search = {int(ef_search)}"))


def _ranked_ids(
    session: Session, sql: str, params: dict, *, mode: str, ef_search: int
) -> tuple[list[uuid.UUID], float]:
    _set_search_mode(session, mode, ef_search)
    start = time.perf_counter()
    rows = session.execute(text(sql), params).all()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return [row[0] for row in rows], elapsed_ms


def _explain(session: Session, sql: str, params: dict, *, mode: str, ef_search: int) -> str:
    _set_search_mode(session, mode, ef_search)
    rows = session.execute(text(f"EXPLAIN ANALYZE {sql}"), params).all()
    return "\n".join(row[0] for row in rows)


@dataclass(frozen=True)
class BenchmarkQuery:
    query_passage_id: uuid.UUID
    company_id: uuid.UUID
    vector: list[float]


def select_deterministic_benchmark_queries(
    app_session: Session, publication_id: uuid.UUID, *, queries_per_company: int = 5
) -> list[BenchmarkQuery]:
    """Up to `queries_per_company` embeddings per company, ordered
    deterministically by (company_id, passage_id) -- no random sampling."""
    from market_documents.publishing.models import Passage as AppPassage

    rows = app_session.execute(
        select(AppPassageEmbedding.passage_id, AppPassage.company_id, AppPassageEmbedding.embedding)
        .join(AppPassage, AppPassage.id == AppPassageEmbedding.passage_id)
        .where(AppPassageEmbedding.publication_id == publication_id)
        .order_by(AppPassage.company_id, AppPassageEmbedding.passage_id)
    ).all()

    queries: list[BenchmarkQuery] = []
    counts: dict[uuid.UUID, int] = {}
    for passage_id, company_id, vector in rows:
        n = counts.get(company_id, 0)
        if n >= queries_per_company:
            continue
        queries.append(
            BenchmarkQuery(query_passage_id=passage_id, company_id=company_id, vector=[float(x) for x in vector])
        )
        counts[company_id] = n + 1
    return queries


@dataclass(frozen=True)
class QueryComparison:
    query_passage_id: uuid.UUID
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


@dataclass(frozen=True)
class RetrievalBenchmarkResult:
    scope: str
    query_count: int
    recall_at_1: float
    recall_at_5: float
    recall_at_10: float
    mean_exact_latency_ms: float
    mean_indexed_latency_ms: float
    indexed_plan_uses_vector_index: bool
    meets_minimum_recall_at_10: bool


def run_unfiltered_benchmark(
    app_session: Session,
    publication_id: uuid.UUID,
    *,
    queries_per_company: int = 5,
    top_k: int = 10,
    ef_search: int = 40,
) -> RetrievalBenchmarkResult:
    """Whole-publication (unfiltered) exact vs. HNSW comparison -- the
    access pattern for a corpus-wide semantic search with no structured
    filters applied."""
    queries = select_deterministic_benchmark_queries(app_session, publication_id, queries_per_company=queries_per_company)
    if not queries:
        raise ValueError("no eligible passage embeddings available to benchmark")

    comparisons: list[QueryComparison] = []
    for q in queries:
        params = {"publication_id": str(publication_id), "vec": _vector_literal(q.vector), "limit": top_k}
        exact_ids, exact_ms = _ranked_ids(app_session, _UNFILTERED_SQL, params, mode="exact", ef_search=ef_search)
        indexed_ids, indexed_ms = _ranked_ids(app_session, _UNFILTERED_SQL, params, mode="hnsw", ef_search=ef_search)
        comparisons.append(
            QueryComparison(
                query_passage_id=q.query_passage_id,
                exact_ids=exact_ids,
                indexed_ids=indexed_ids,
                exact_latency_ms=exact_ms,
                indexed_latency_ms=indexed_ms,
            )
        )

    sample = queries[0]
    sample_params = {"publication_id": str(publication_id), "vec": _vector_literal(sample.vector), "limit": top_k}
    indexed_plan = _explain(app_session, _UNFILTERED_SQL, sample_params, mode="hnsw", ef_search=ef_search)

    recall_at_10 = statistics.fmean(c.recall_at(10) for c in comparisons)
    return RetrievalBenchmarkResult(
        scope="unfiltered",
        query_count=len(comparisons),
        recall_at_1=statistics.fmean(c.recall_at(1) for c in comparisons),
        recall_at_5=statistics.fmean(c.recall_at(5) for c in comparisons),
        recall_at_10=recall_at_10,
        mean_exact_latency_ms=statistics.fmean(c.exact_latency_ms for c in comparisons),
        mean_indexed_latency_ms=statistics.fmean(c.indexed_latency_ms for c in comparisons),
        indexed_plan_uses_vector_index=VECTOR_INDEX_NAME in indexed_plan,
        meets_minimum_recall_at_10=recall_at_10 >= MINIMUM_INDEXED_RECALL_AT_10,
    )


def run_company_filtered_benchmark(
    app_session: Session,
    publication_id: uuid.UUID,
    company_id: uuid.UUID,
    *,
    top_k: int = 10,
    ef_search: int = 40,
) -> RetrievalBenchmarkResult:
    """Company-pre-filtered exact vs. HNSW comparison -- representative of a
    selective structured filter applied before vector ranking."""
    from market_documents.publishing.models import Passage as AppPassage

    rows = app_session.execute(
        select(AppPassageEmbedding.passage_id, AppPassageEmbedding.embedding)
        .join(AppPassage, AppPassage.id == AppPassageEmbedding.passage_id)
        .where(AppPassageEmbedding.publication_id == publication_id, AppPassage.company_id == company_id)
        .order_by(AppPassageEmbedding.passage_id)
        .limit(5)
    ).all()
    if not rows:
        raise ValueError(f"no eligible passage embeddings for company {company_id}")

    comparisons: list[QueryComparison] = []
    for passage_id, vector in rows:
        vec = [float(x) for x in vector]
        params = {
            "publication_id": str(publication_id),
            "company_id": str(company_id),
            "vec": _vector_literal(vec),
            "limit": top_k,
        }
        exact_ids, exact_ms = _ranked_ids(app_session, _COMPANY_FILTERED_SQL, params, mode="exact", ef_search=ef_search)
        indexed_ids, indexed_ms = _ranked_ids(
            app_session, _COMPANY_FILTERED_SQL, params, mode="hnsw", ef_search=ef_search
        )
        comparisons.append(
            QueryComparison(
                query_passage_id=passage_id,
                exact_ids=exact_ids,
                indexed_ids=indexed_ids,
                exact_latency_ms=exact_ms,
                indexed_latency_ms=indexed_ms,
            )
        )

    sample_passage_id, sample_vector = rows[0]
    sample_params = {
        "publication_id": str(publication_id),
        "company_id": str(company_id),
        "vec": _vector_literal([float(x) for x in sample_vector]),
        "limit": top_k,
    }
    indexed_plan = _explain(app_session, _COMPANY_FILTERED_SQL, sample_params, mode="hnsw", ef_search=ef_search)

    recall_at_10 = statistics.fmean(c.recall_at(10) for c in comparisons)
    return RetrievalBenchmarkResult(
        scope=f"company:{company_id}",
        query_count=len(comparisons),
        recall_at_1=statistics.fmean(c.recall_at(1) for c in comparisons),
        recall_at_5=statistics.fmean(c.recall_at(5) for c in comparisons),
        recall_at_10=recall_at_10,
        mean_exact_latency_ms=statistics.fmean(c.exact_latency_ms for c in comparisons),
        mean_indexed_latency_ms=statistics.fmean(c.indexed_latency_ms for c in comparisons),
        indexed_plan_uses_vector_index=VECTOR_INDEX_NAME in indexed_plan,
        meets_minimum_recall_at_10=recall_at_10 >= MINIMUM_INDEXED_RECALL_AT_10,
    )
