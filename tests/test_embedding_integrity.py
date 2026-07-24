"""Embedding integrity: NaN/Infinity rejection at the storage layer,
zero-vector detection, configuration-hash sensitivity, and the guarantee
that a passage-content change never silently reuses a stale embedding.

Mirrors `test_passage_migration.py::test_vector_dimension_is_enforced`'s
temp-table pattern for the storage-layer checks, and
`test_passage_embedding.py`'s fixture helpers for the content-change test.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError

from market_documents.models.company import Company
from market_documents.models.embedding import EMBEDDING_DIMENSION, EmbeddingRun, PassageEmbedding
from market_documents.models.enums import (
    BlockType,
    EmbeddingRunStatus,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    PassageSegmentationRunStatus,
    PassageType,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument, Page, TextBlock
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.services import passage_embedding as pe
from market_documents.services import passage_segmentation as ps
from market_documents.services.embedding_config import EmbeddingConfig, compute_configuration_hash
from market_documents.services.embedding_integrity import check_embedding_integrity
from market_documents.services.narrative_construction import build_narrative_text, compute_content_hash


def test_nan_embedding_is_rejected(db_session):
    db_session.execute(text(f"CREATE TEMP TABLE test_nan_vec (v vector({EMBEDDING_DIMENSION}))")).close()
    nan_literal = "[" + ",".join(["NaN"] + ["0.1"] * (EMBEDDING_DIMENSION - 1)) + "]"
    with pytest.raises(DataError):
        db_session.execute(text("INSERT INTO test_nan_vec (v) VALUES (:v)"), {"v": nan_literal})


def test_infinite_embedding_is_rejected(db_session):
    db_session.execute(text(f"CREATE TEMP TABLE test_inf_vec (v vector({EMBEDDING_DIMENSION}))")).close()
    inf_literal = "[" + ",".join(["Infinity"] + ["0.1"] * (EMBEDDING_DIMENSION - 1)) + "]"
    with pytest.raises(DataError):
        db_session.execute(text("INSERT INTO test_inf_vec (v) VALUES (:v)"), {"v": inf_literal})


def test_zero_vector_is_stored_but_flagged_by_integrity_check(db_session):
    """Postgres itself allows an all-zero vector (unlike NaN/Infinity), so
    `check_embedding_integrity` -- not a DB constraint -- is what must catch
    it, against the real `passage_embeddings` table."""
    company = Company(ticker="ZEROV", company_name="Zero Vector Test Co")
    db_session.add(company)
    db_session.flush()
    report = Report(
        company_id=company.id, local_path="data/raw/ZEROV/2023/annual.pdf", filename="annual.pdf",
        sha256=compute_content_hash("zerov"), directory_year=2023, metadata_status=MetadataStatus.VALIDATED,
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
        word_count=1, content_hash=compute_content_hash("zerov-text"),
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
    passage = Passage(
        segmentation_run_id=segmentation_run.id, narrative_document_id=narrative.id, report_id=report.id,
        extraction_run_id=extraction_run.id, passage_index=0, raw_text="x", normalized_text="x",
        content_hash=compute_content_hash("zerov-passage"), first_page_number=1, last_page_number=1,
        word_count=1, token_count=1, character_count=1, passage_type=PassageType.PARAGRAPH,
        excluded_from_alignment=False,
    )
    db_session.add(passage)
    db_session.flush()
    embedding_run = EmbeddingRun(
        segmentation_run_id=segmentation_run.id, model_name="test-model", model_revision="rev1",
        tokenizer_name="test-model", tokenizer_revision="rev1", embedding_dimension=EMBEDDING_DIMENSION,
        pooling_strategy="cls", normalization_method="l2", maximum_model_tokens=512,
        configuration_hash="emb-hash", status=EmbeddingRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    db_session.add(embedding_run)
    db_session.flush()

    before = check_embedding_integrity(db_session)

    zero_embedding = PassageEmbedding(
        embedding_run_id=embedding_run.id, passage_id=passage.id, embedding=[0.0] * EMBEDDING_DIMENSION,
        input_token_count=1, truncated=False,
    )
    db_session.add(zero_embedding)
    db_session.flush()

    after = check_embedding_integrity(db_session)
    assert after.zero_vector_count == before.zero_vector_count + 1
    assert str(passage.id) in after.zero_vector_passage_ids


def test_embedding_config_hash_changes_with_pooling_strategy():
    base = compute_configuration_hash(EmbeddingConfig(pooling_strategy="cls"))
    changed = compute_configuration_hash(EmbeddingConfig(pooling_strategy="mean"))
    assert base != changed


def test_embedding_config_hash_changes_with_normalization_method():
    base = compute_configuration_hash(EmbeddingConfig(normalization_method="l2"))
    changed = compute_configuration_hash(EmbeddingConfig(normalization_method="none"))
    assert base != changed


def test_embedding_config_hash_changes_with_model_revision():
    base = compute_configuration_hash(EmbeddingConfig(model_revision="rev1"))
    changed = compute_configuration_hash(EmbeddingConfig(model_revision="rev2"))
    assert base != changed


class FakeEmbeddingModel:
    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def encode_batch(self, texts: list[str]) -> list[pe.EncodedPassage]:
        return [
            pe.EncodedPassage(vector=[0.1] * EMBEDDING_DIMENSION, input_token_count=self.count_tokens(t), truncated=False)
            for t in texts
        ]


def _words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def _extraction_and_narrative(db_session, report, *, body_words: int, suffix: str):
    """A fresh ExtractionRun + NarrativeDocument for `report`, simulating a
    re-extraction after the underlying PDF/content changed."""
    extraction_run = ExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash=f"test-hash-{suffix}",
        status=ExtractionStatus.COMPLETED, extraction_quality=ExtractionQuality.GOOD,
        started_at=datetime.now(UTC), completed_at=datetime.now(UTC), encrypted_pdf_handled=False,
    )
    db_session.add(extraction_run)
    db_session.flush()

    page = Page(
        extraction_run_id=extraction_run.id, report_id=report.id, page_number=1, raw_text="text",
        cleaned_text="text", character_count=4, word_count=1, block_count=2,
        native_text_available=True, suspected_image_only=False, extraction_quality=ExtractionQuality.GOOD,
    )
    db_session.add(page)
    db_session.flush()

    db_session.add(
        TextBlock(
            extraction_run_id=extraction_run.id, page_id=page.id, report_id=report.id,
            block_index=0, reading_order=0, raw_text="Overview", cleaned_text="Overview",
            block_type=BlockType.HEADING_CANDIDATE,
        )
    )
    db_session.add(
        TextBlock(
            extraction_run_id=extraction_run.id, page_id=page.id, report_id=report.id,
            block_index=1, reading_order=1, raw_text=_words(body_words), cleaned_text=_words(body_words),
            block_type=BlockType.PARAGRAPH,
        )
    )
    db_session.flush()

    narrative_text = build_narrative_text(db_session, extraction_run.id)
    narrative = NarrativeDocument(
        extraction_run_id=extraction_run.id, report_id=report.id, cleaned_text=narrative_text,
        word_count=len(narrative_text.split()), content_hash=compute_content_hash(narrative_text),
    )
    db_session.add(narrative)
    db_session.flush()
    return extraction_run, narrative


def test_passage_content_change_triggers_a_new_embedding_run_not_stale_reuse(db_session):
    """A changed PDF/content flows through a brand-new ExtractionRun (a
    different `extraction_run_id`), which makes `segment_report` create a
    fresh `PassageSegmentationRun` regardless of unchanged segmentation
    config (see `passage_segmentation.py`'s skip check, gated on
    `extraction_run_id` equality too) -- and since `EmbeddingRun` lookup is
    keyed by `segmentation_run_id`, embedding that new run can never reuse
    the old embedding run, even with an identical `EmbeddingConfig`."""
    company = Company(ticker="CCHG", company_name="Content Change Test Co")
    db_session.add(company)
    db_session.flush()
    report = Report(
        company_id=company.id, local_path="data/raw/CCHG/2023/annual.pdf", filename="annual.pdf",
        sha256=compute_content_hash("cchg"), directory_year=2023, metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()

    _, narrative_v1 = _extraction_and_narrative(db_session, report, body_words=80, suffix="v1")
    outcome_v1 = ps.segment_report(db_session, report)
    assert outcome_v1.run is not None
    embed_outcome_v1 = pe.embed_segmentation_run(db_session, outcome_v1.run, model=FakeEmbeddingModel())
    assert embed_outcome_v1.run is not None

    _, narrative_v2 = _extraction_and_narrative(db_session, report, body_words=120, suffix="v2")
    assert narrative_v2.content_hash != narrative_v1.content_hash
    outcome_v2 = ps.segment_report(db_session, report)
    assert outcome_v2.run is not None
    assert outcome_v2.run.id != outcome_v1.run.id
    assert outcome_v2.skipped is False

    embed_outcome_v2 = pe.embed_segmentation_run(db_session, outcome_v2.run, model=FakeEmbeddingModel())

    assert embed_outcome_v2.skipped is False
    assert embed_outcome_v2.run is not None
    assert embed_outcome_v2.run.id != embed_outcome_v1.run.id
    assert embed_outcome_v2.run.segmentation_run_id == outcome_v2.run.id
