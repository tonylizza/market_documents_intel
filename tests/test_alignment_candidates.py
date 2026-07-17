import math
import uuid
from datetime import UTC, datetime

import pytest

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


def _vec(similarity_to_e0: float, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    """A unit vector whose cosine similarity to the canonical base vector e0
    (used as the "later passage" query vector in these tests) is exactly
    `similarity_to_e0`."""
    theta = math.acos(max(-1.0, min(1.0, similarity_to_e0)))
    v = [0.0] * dim
    v[0] = math.cos(theta)
    v[1] = math.sin(theta)
    return v


BASE_VEC = _vec(1.0)


def _report_and_run(db_session, ticker: str):
    company = Company(ticker=ticker, company_name="Candidate Test Co")
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
        started_at=datetime.now(UTC), completed_at=datetime.now(UTC), encrypted_pdf_handled=False,
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
        status=PassageSegmentationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    db_session.add(segmentation_run)
    db_session.flush()

    embedding_run = EmbeddingRun(
        segmentation_run_id=segmentation_run.id, model_name="test-model", model_revision="rev1",
        tokenizer_name="test-model", tokenizer_revision="rev1", embedding_dimension=EMBEDDING_DIMENSION,
        pooling_strategy="cls", normalization_method="l2", maximum_model_tokens=512,
        configuration_hash="emb-hash", status=EmbeddingRunStatus.COMPLETED, completed_at=datetime.now(UTC),
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
        content_hash=compute_content_hash(f"passage-{index}-{uuid.uuid4()}"),
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


def test_candidates_ordered_by_cosine_similarity_descending(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "CAND1")
    p_high = _passage(db_session, seg_run, report, index=0)
    p_mid = _passage(db_session, seg_run, report, index=1)
    p_low = _passage(db_session, seg_run, report, index=2)
    _embedding(db_session, emb_run, p_high, _vec(0.95))
    _embedding(db_session, emb_run, p_mid, _vec(0.70))
    _embedding(db_session, emb_run, p_low, _vec(0.10))

    candidates = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=5, min_semantic_similarity=0.0,
    )
    assert [c.passage.id for c in candidates] == [p_high.id, p_mid.id, p_low.id]
    assert candidates[0].semantic_similarity == pytest.approx(0.95, abs=1e-4)


def test_candidates_respect_top_k(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "CAND2")
    for i in range(5):
        p = _passage(db_session, seg_run, report, index=i)
        _embedding(db_session, emb_run, p, _vec(0.9 - i * 0.1))

    candidates = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=2, min_semantic_similarity=0.0,
    )
    assert len(candidates) == 2


def test_candidates_respect_minimum_similarity_threshold(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "CAND3")
    p_above = _passage(db_session, seg_run, report, index=0)
    p_below = _passage(db_session, seg_run, report, index=1)
    _embedding(db_session, emb_run, p_above, _vec(0.80))
    _embedding(db_session, emb_run, p_below, _vec(0.30))

    candidates = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=5, min_semantic_similarity=0.5,
    )
    assert [c.passage.id for c in candidates] == [p_above.id]


def test_candidates_exclude_excluded_passages(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "CAND4")
    p_included = _passage(db_session, seg_run, report, index=0)
    p_excluded = _passage(db_session, seg_run, report, index=1, excluded=True)
    _embedding(db_session, emb_run, p_included, _vec(0.9))
    _embedding(db_session, emb_run, p_excluded, _vec(0.95))  # would rank first if not excluded

    candidates = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=5, min_semantic_similarity=0.0,
    )
    assert [c.passage.id for c in candidates] == [p_included.id]


def test_candidates_restricted_to_specified_embedding_run(db_session):
    report_a, seg_run_a, emb_run_a = _report_and_run(db_session, "CAND5A")
    report_b, seg_run_b, emb_run_b = _report_and_run(db_session, "CAND5B")
    p_a = _passage(db_session, seg_run_a, report_a, index=0)
    p_b = _passage(db_session, seg_run_b, report_b, index=0)
    _embedding(db_session, emb_run_a, p_a, _vec(0.9))
    _embedding(db_session, emb_run_b, p_b, _vec(0.99))  # higher similarity, but wrong (other report's) run

    candidates = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run_a.id,
        top_k=5, min_semantic_similarity=0.0,
    )
    assert [c.passage.id for c in candidates] == [p_a.id]


def test_candidates_deterministic_tie_break_by_passage_index(db_session):
    report, seg_run, emb_run = _report_and_run(db_session, "CAND6")
    p_second = _passage(db_session, seg_run, report, index=5)
    p_first = _passage(db_session, seg_run, report, index=1)
    same_vec = _vec(0.5)
    _embedding(db_session, emb_run, p_second, same_vec)
    _embedding(db_session, emb_run, p_first, same_vec)

    candidates = get_semantic_candidates(
        db_session, later_embedding_vector=BASE_VEC, earlier_embedding_run_id=emb_run.id,
        top_k=5, min_semantic_similarity=0.0,
    )
    assert [c.passage.passage_index for c in candidates] == [1, 5]
