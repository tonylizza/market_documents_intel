"""Milestone 4 completion: HNSW vector index migration, operator class,
exact-vs-indexed retrieval, and the deterministic retrieval benchmark.

Mirrors `test_passage_migration.py`'s round-trip pattern and
`test_alignment_candidates.py`'s fixture helpers (`_vec`, `_report_and_run`,
`_passage`, `_embedding`), but exercises `search_mode=HNSW` alongside the
existing EXACT-mode coverage.
"""

import math
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from market_documents.models.company import Company
from market_documents.models.embedding import EMBEDDING_DIMENSION, EmbeddingRun, PassageEmbedding
from market_documents.models.enums import (
    EmbeddingRunStatus,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    PassageSegmentationRunStatus,
    PassageType,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.services.alignment_candidates import get_semantic_candidates
from market_documents.services.narrative_construction import compute_content_hash
from market_documents.services.retrieval_benchmark import run_retrieval_benchmark
from market_documents.services.retrieval_config import (
    RetrievalConfig,
    VectorSearchMode,
    compute_retrieval_configuration_hash,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
M4_HNSW_PARENT_REVISION = "2caf70d7f084"
VECTOR_INDEX_NAME = "ix_passage_embeddings_embedding_hnsw_cosine"


def _vec(similarity_to_e0: float, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    """A unit vector whose cosine similarity to the canonical base vector e0
    (BASE_VEC, used as the "later passage" query vector) is exactly
    `similarity_to_e0`. Mirrors `test_alignment_candidates.py`'s helper."""
    theta = math.acos(max(-1.0, min(1.0, similarity_to_e0)))
    v = [0.0] * dim
    v[0] = math.cos(theta)
    v[1] = math.sin(theta)
    return v


BASE_VEC = _vec(1.0)


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _index_names(engine) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'passage_embeddings'"))
        return {row[0] for row in rows}


def _index_def(engine, name: str) -> str:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"), {"name": name}
        ).first()
        return row[0]


def test_hnsw_index_migration_upgrade_creates_index(engine):
    assert VECTOR_INDEX_NAME in _index_names(engine)


def test_hnsw_index_migration_downgrade_removes_index_then_reupgrade_restores_it(engine):
    cfg = _alembic_config()

    command.downgrade(cfg, M4_HNSW_PARENT_REVISION)
    assert VECTOR_INDEX_NAME not in _index_names(engine)

    command.upgrade(cfg, "head")
    assert VECTOR_INDEX_NAME in _index_names(engine)


def test_hnsw_index_uses_cosine_operator_class(engine):
    indexdef = _index_def(engine, VECTOR_INDEX_NAME)
    assert "USING hnsw" in indexdef
    assert "vector_cosine_ops" in indexdef


def _report_and_run(db_session, ticker: str):
    company = Company(ticker=ticker, company_name="Vector Index Test Co")
    db_session.add(company)
    db_session.flush()

    report = Report(
        company_id=company.id,
        local_path=f"data/raw/{ticker}/2023/annual.pdf",
        filename="annual.pdf",
        sha256=compute_content_hash(ticker),
        directory_year=2023,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()

    extraction_run = ExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="test-hash",
        status=ExtractionStatus.COMPLETED, extraction_quality=ExtractionQuality.GOOD,
        started_at=None, completed_at=None, encrypted_pdf_handled=False,
    )
    db_session.add(extraction_run)
    db_session.flush()

    narrative = NarrativeDocument(
        extraction_run_id=extraction_run.id, report_id=report.id, cleaned_text="text",
        word_count=1, content_hash=compute_content_hash("text"),
    )
    db_session.add(narrative)
    db_session.flush()

    segmentation_run = PassageSegmentationRun(
        narrative_document_id=narrative.id, extraction_run_id=extraction_run.id,
        algorithm_version="1.0.0", configuration_hash="seg-hash",
        status=PassageSegmentationRunStatus.COMPLETED, completed_at=None,
    )
    db_session.add(segmentation_run)
    db_session.flush()

    embedding_run = EmbeddingRun(
        segmentation_run_id=segmentation_run.id, model_name="test-model", model_revision="rev1",
        tokenizer_name="test-model", tokenizer_revision="rev1", embedding_dimension=EMBEDDING_DIMENSION,
        pooling_strategy="cls", normalization_method="l2", maximum_model_tokens=512,
        configuration_hash="emb-hash", status=EmbeddingRunStatus.COMPLETED, completed_at=None,
    )
    db_session.add(embedding_run)
    db_session.flush()

    return report, segmentation_run, embedding_run


def _passage(db_session, segmentation_run, report, *, index: int, excluded: bool = False) -> Passage:
    passage = Passage(
        segmentation_run_id=segmentation_run.id,
        narrative_document_id=segmentation_run.narrative_document_id,
        report_id=report.id,
        extraction_run_id=segmentation_run.extraction_run_id,
        passage_index=index,
        raw_text=f"passage {index} text",
        normalized_text=f"passage {index} text",
        content_hash=compute_content_hash(f"passage-{index}-{report.id}"),
        first_page_number=1,
        last_page_number=1,
        word_count=10,
        token_count=10,
        character_count=50,
        heading_text=None,
        passage_type=PassageType.PARAGRAPH,
        excluded_from_alignment=excluded,
    )
    db_session.add(passage)
    db_session.flush()
    return passage


def _embedding(db_session, embedding_run, passage, vector: list[float]) -> PassageEmbedding:
    embedding = PassageEmbedding(
        embedding_run_id=embedding_run.id, passage_id=passage.id, embedding=vector,
        input_token_count=10, truncated=False,
    )
    db_session.add(embedding)
    db_session.flush()
    return embedding


def test_indexed_retrieval_matches_exact_retrieval(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "VIDX1")
    p_high = _passage(db_session, seg_run, report, index=0)
    p_mid = _passage(db_session, seg_run, report, index=1)
    p_low = _passage(db_session, seg_run, report, index=2)
    _embedding(db_session, emb_run, p_high, _vec(0.95))
    _embedding(db_session, emb_run, p_mid, _vec(0.70))
    _embedding(db_session, emb_run, p_low, _vec(0.10))

    exact = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=5, min_semantic_similarity=0.0, search_mode=VectorSearchMode.EXACT,
    )
    indexed = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=5, min_semantic_similarity=0.0, search_mode=VectorSearchMode.HNSW,
    )
    assert [c.passage.id for c in indexed] == [c.passage.id for c in exact] == [p_high.id, p_mid.id, p_low.id]


def test_indexed_retrieval_is_restricted_to_specified_embedding_run(db_session):
    report_a, seg_run_a, emb_run_a = _report_and_run(db_session, "VIDX2A")
    report_b, seg_run_b, emb_run_b = _report_and_run(db_session, "VIDX2B")
    p_a = _passage(db_session, seg_run_a, report_a, index=0)
    p_b = _passage(db_session, seg_run_b, report_b, index=0)
    _embedding(db_session, emb_run_a, p_a, _vec(0.9))
    _embedding(db_session, emb_run_b, p_b, _vec(0.99))  # higher similarity, but the wrong (other report's) run

    indexed = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run_a.id,
        top_k=5, min_semantic_similarity=0.0, search_mode=VectorSearchMode.HNSW,
    )
    assert [c.passage.id for c in indexed] == [p_a.id]


def test_indexed_retrieval_deterministic_tie_break_by_passage_index(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "VIDX3")
    p_second = _passage(db_session, seg_run, report, index=5)
    p_first = _passage(db_session, seg_run, report, index=1)
    same_vec = _vec(0.5)
    _embedding(db_session, emb_run, p_second, same_vec)
    _embedding(db_session, emb_run, p_first, same_vec)

    indexed = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=5, min_semantic_similarity=0.0, search_mode=VectorSearchMode.HNSW,
    )
    assert [c.passage.passage_index for c in indexed] == [1, 5]


def test_indexed_retrieval_returns_all_available_when_fewer_than_top_k(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "VIDX4")
    p1 = _passage(db_session, seg_run, report, index=0)
    p2 = _passage(db_session, seg_run, report, index=1)
    _embedding(db_session, emb_run, p1, _vec(0.9))
    _embedding(db_session, emb_run, p2, _vec(0.8))

    indexed = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=10, min_semantic_similarity=0.0, search_mode=VectorSearchMode.HNSW,
    )
    assert len(indexed) == 2


def test_retrieval_benchmark_reports_full_recall_on_small_deterministic_corpus(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "VBENCH")
    for i in range(12):
        _passage_and_embedding = _passage(db_session, seg_run, report, index=i)
        _embedding(db_session, emb_run, _passage_and_embedding, _vec(0.9 - i * 0.05))

    result = run_retrieval_benchmark(db_session, queries_per_run=3, top_k=5)

    assert result.query_count == 3
    assert 0.0 <= result.recall_at_1 <= 1.0
    assert 0.0 <= result.recall_at_5 <= 1.0
    assert 0.0 <= result.recall_at_10 <= 1.0
    assert result.recall_at_1 == 1.0  # each query passage's own vector is its own exact nearest neighbor
    assert result.mean_exact_latency_ms >= 0.0
    assert result.mean_indexed_latency_ms >= 0.0


def test_retrieval_benchmark_raises_without_eligible_embeddings(db_session):
    with pytest.raises(ValueError):
        run_retrieval_benchmark(db_session)


def test_retrieval_config_hash_changes_with_search_mode():
    exact_hash = compute_retrieval_configuration_hash(RetrievalConfig(vector_search_mode=VectorSearchMode.EXACT))
    hnsw_hash = compute_retrieval_configuration_hash(RetrievalConfig(vector_search_mode=VectorSearchMode.HNSW))
    assert exact_hash != hnsw_hash


def test_retrieval_config_hash_changes_with_candidate_limit_and_ef_search():
    base = compute_retrieval_configuration_hash(RetrievalConfig(candidate_limit=50, hnsw_ef_search=40))
    different_limit = compute_retrieval_configuration_hash(RetrievalConfig(candidate_limit=100, hnsw_ef_search=40))
    different_ef = compute_retrieval_configuration_hash(RetrievalConfig(candidate_limit=50, hnsw_ef_search=80))
    assert base != different_limit
    assert base != different_ef
