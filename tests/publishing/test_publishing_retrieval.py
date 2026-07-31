"""Milestone 7B.1: passage embeddings and comparison-aware retrieval
contexts.

Uses the same `_feature_fixtures.build_ready_pair` real end-to-end fixture
as `test_publishing_lifecycle.py`/`test_publishing_disclosure_change_
quality.py` for matched/NEW/REMOVED cases (it already creates real research
`PassageEmbedding` rows -- see `_embed` in that module), plus a small local
solo-report builder for the REPORT_ONLY and missing-embedding cases, which
`build_ready_pair` cannot produce (it always creates a fully-aligned pair).
"""

import math
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _feature_fixtures import build_manual_alignment_pair, build_ready_pair  # noqa: E402

from market_documents.models.company import Company
from market_documents.models.embedding import EMBEDDING_DIMENSION, EmbeddingRun, PassageEmbedding
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentStatus,
    EmbeddingRunStatus,
    ExtractionStatus,
    ExtractionQuality,
    MetadataStatus,
    PassageSegmentationRunStatus,
    PassageType,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.publishing.models import Passage as AppPassage
from market_documents.publishing.models import PassageEmbedding as AppPassageEmbedding
from market_documents.publishing.models import PublicationStatus, RetrievalContext
from market_documents.publishing.publisher import PublicationBuilder
from market_documents.services.feature_extraction import build_features
from market_documents.services.narrative_construction import compute_content_hash


def _vec(seed: float) -> list[float]:
    v = [0.0] * EMBEDDING_DIMENSION
    v[0] = math.cos(seed)
    v[1] = math.sin(seed)
    return v


def _build_and_feature(db_session, ticker: str, **kwargs):
    pair, alignment_outcome, _similarity_outcome = build_ready_pair(db_session, ticker=ticker, **kwargs)
    build_features(db_session, pair)
    db_session.flush()
    return pair, alignment_outcome


def _build_solo_report(db_session, *, ticker: str, texts: list[str], embed: bool) -> Report:
    """One company, one report, one segmentation run, N passages -- never
    referenced by any ReportPair, so its passages can never occupy a
    passage-comparison side. Used for the REPORT_ONLY and missing-embedding
    validation cases, which `build_ready_pair` cannot produce."""
    company = Company(ticker=ticker, company_name=f"{ticker} Solo Co")
    db_session.add(company)
    db_session.flush()

    report = Report(
        company_id=company.id,
        local_path=f"data/raw/{ticker}/2023/solo.pdf",
        filename="solo.pdf",
        sha256=compute_content_hash(f"{ticker}-solo"),
        directory_year=2023,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()

    extraction = ExtractionRun(
        report_id=report.id,
        extractor_name="test",
        extractor_version="1",
        configuration_hash="test-hash",
        status=ExtractionStatus.COMPLETED,
        extraction_quality=ExtractionQuality.GOOD,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        encrypted_pdf_handled=False,
    )
    db_session.add(extraction)
    db_session.flush()

    joined_text = " ".join(texts)
    narrative = NarrativeDocument(
        extraction_run_id=extraction.id,
        report_id=report.id,
        cleaned_text=joined_text,
        word_count=len(joined_text.split()),
        content_hash=compute_content_hash(f"narrative-{extraction.id}"),
    )
    db_session.add(narrative)
    db_session.flush()

    seg = PassageSegmentationRun(
        narrative_document_id=narrative.id,
        extraction_run_id=extraction.id,
        algorithm_version="1.0.0",
        configuration_hash="seg-hash",
        status=PassageSegmentationRunStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    db_session.add(seg)
    db_session.flush()

    embedding_run = EmbeddingRun(
        segmentation_run_id=seg.id,
        model_name="test-model",
        model_revision="rev1",
        tokenizer_name="test-model",
        tokenizer_revision="rev1",
        embedding_dimension=EMBEDDING_DIMENSION,
        pooling_strategy="cls",
        normalization_method="l2",
        maximum_model_tokens=512,
        configuration_hash="emb-hash",
        status=EmbeddingRunStatus.COMPLETED,
        completed_at=datetime.now(UTC),
        embedded_passage_count=0,
        skipped_passage_count=0,
    )
    db_session.add(embedding_run)
    db_session.flush()

    for index, text in enumerate(texts):
        passage = Passage(
            segmentation_run_id=seg.id,
            narrative_document_id=narrative.id,
            report_id=report.id,
            extraction_run_id=extraction.id,
            passage_index=index,
            raw_text=text,
            normalized_text=text.lower(),
            content_hash=compute_content_hash(f"{text}-{index}-{seg.id}"),
            first_page_number=1,
            last_page_number=1,
            word_count=len(text.split()),
            token_count=len(text.split()),
            character_count=len(text),
            heading_text=None,
            passage_type=PassageType.PARAGRAPH,
            excluded_from_alignment=False,
        )
        db_session.add(passage)
        db_session.flush()
        if embed:
            db_session.add(
                PassageEmbedding(
                    embedding_run_id=embedding_run.id,
                    passage_id=passage.id,
                    embedding=_vec(index + 1),
                    input_token_count=5,
                    truncated=False,
                )
            )
            embedding_run.embedded_passage_count = (embedding_run.embedded_passage_count or 0) + 1
    db_session.flush()
    return report


def test_matched_comparison_produces_two_contexts(db_session, app_db_session):
    _build_and_feature(db_session, ticker="RET1")
    builder = PublicationBuilder(publication_version="ret-test-v1")
    publication = builder.build(db_session, app_db_session)

    assert publication.status == PublicationStatus.READY.value, publication.failure_reason
    app_passages = list(
        app_db_session.scalars(select(AppPassage).where(AppPassage.publication_id == publication.id))
    )
    assert len(app_passages) == 2  # one matched passage per side

    embeddings = list(
        app_db_session.scalars(select(AppPassageEmbedding).where(AppPassageEmbedding.publication_id == publication.id))
    )
    assert len(embeddings) == 2  # deduplicated: one vector per passage

    contexts = list(
        app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == publication.id))
    )
    assert len(contexts) == 2  # matched status -> earlier-side + later-side
    sides = {c.report_side for c in contexts}
    assert sides == {"EARLIER", "LATER"}
    for c in contexts:
        assert c.context_type == "COMPARISON_LINKED"
        assert c.passage_comparison_id is not None
        assert c.report_comparison_id is not None


def test_new_status_produces_later_side_context_only(db_session, app_db_session):
    # `build_manual_alignment_pair` hand-specifies alignment_status directly
    # (bypassing the real alignment algorithm's confidence thresholds, which
    # can classify a genuinely-unmatched passage as AMBIGUOUS rather than a
    # confident NEW/REMOVED) -- the deterministic side rule under test here
    # is the publisher's, not the alignment algorithm's.
    base_text = " ".join(["matched"] * 45)
    pair, _alignment_run, _earlier, _later = build_manual_alignment_pair(
        db_session,
        ticker="RET2",
        earlier_texts=[(base_text, PassageType.PARAGRAPH)],
        later_texts=[(base_text, PassageType.PARAGRAPH), ("brand new disclosure language", PassageType.PARAGRAPH)],
        rows=[
            {"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
            {"earlier": None, "later": 1, "status": AlignmentStatus.NEW, "confidence": AlignmentConfidence.HIGH},
        ],
    )[:4]
    build_features(db_session, pair)
    db_session.flush()

    builder = PublicationBuilder(publication_version="ret-test-v2")
    publication = builder.build(db_session, app_db_session)
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason

    contexts = list(
        app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == publication.id))
    )
    new_contexts = [c for c in contexts if c.alignment_status == "NEW"]
    assert len(new_contexts) == 1
    assert new_contexts[0].report_side == "LATER"


def test_removed_status_produces_earlier_side_context_only(db_session, app_db_session):
    base_text = " ".join(["matched"] * 45)
    pair, _alignment_run, _earlier, _later = build_manual_alignment_pair(
        db_session,
        ticker="RET3",
        earlier_texts=[(base_text, PassageType.PARAGRAPH), ("language that will disappear", PassageType.PARAGRAPH)],
        later_texts=[(base_text, PassageType.PARAGRAPH)],
        rows=[
            {"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
            {"earlier": 1, "later": None, "status": AlignmentStatus.REMOVED, "confidence": AlignmentConfidence.HIGH},
        ],
    )[:4]
    build_features(db_session, pair)
    db_session.flush()

    builder = PublicationBuilder(publication_version="ret-test-v3")
    publication = builder.build(db_session, app_db_session)
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason

    contexts = list(
        app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == publication.id))
    )
    removed_contexts = [c for c in contexts if c.alignment_status == "REMOVED"]
    assert len(removed_contexts) == 1
    assert removed_contexts[0].report_side == "EARLIER"


def test_rebuild_same_version_embeddings_and_contexts_idempotent(db_session, app_db_session):
    _build_and_feature(db_session, ticker="RET4")
    builder = PublicationBuilder(publication_version="ret-test-v4-idempotent")

    first = builder.build(db_session, app_db_session)
    first_embedding_ids = {
        e.id for e in app_db_session.scalars(select(AppPassageEmbedding).where(AppPassageEmbedding.publication_id == first.id))
    }
    first_context_ids = {
        c.id for c in app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == first.id))
    }

    from market_documents.publishing.models import Publication

    app_db_session.delete(app_db_session.get(Publication, first.id))
    app_db_session.flush()

    second = builder.build(db_session, app_db_session)
    second_embedding_ids = {
        e.id for e in app_db_session.scalars(select(AppPassageEmbedding).where(AppPassageEmbedding.publication_id == second.id))
    }
    second_context_ids = {
        c.id for c in app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == second.id))
    }
    assert first_embedding_ids == second_embedding_ids
    assert first_context_ids == second_context_ids


def test_report_only_context_for_passage_with_no_comparison(db_session, app_db_session):
    _build_solo_report(db_session, ticker="RET5", texts=["a solo unmatched disclosure passage"], embed=True)
    builder = PublicationBuilder(publication_version="ret-test-v5")
    publication = builder.build(db_session, app_db_session)
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason

    contexts = list(
        app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == publication.id))
    )
    report_only = [c for c in contexts if c.context_type == "REPORT_ONLY"]
    assert len(report_only) == 1
    assert report_only[0].passage_comparison_id is None
    assert report_only[0].report_comparison_id is None
    assert report_only[0].report_side is None


def test_missing_source_embedding_fails_validation(db_session, app_db_session):
    _build_solo_report(db_session, ticker="RET6", texts=["a passage with no embedding at all"], embed=False)
    builder = PublicationBuilder(publication_version="ret-test-v6")
    publication = builder.build(db_session, app_db_session)

    assert publication.status == PublicationStatus.FAILED.value
    failure_checks = {f["check"] for f in publication.validation_summary["failures"]}
    assert "embedding_coverage_meets_minimum" in failure_checks


def test_cleanup_removes_embeddings_and_contexts(db_session, app_db_session):
    _build_and_feature(db_session, ticker="RET7")
    builder = PublicationBuilder(publication_version="ret-test-v7")
    publication = builder.build(db_session, app_db_session)
    publication_id = publication.id

    from market_documents.publishing.publisher import cleanup_publications

    removed = cleanup_publications(app_db_session, keep=0, dry_run=False)
    assert publication_id in {p.id for p in removed}

    remaining_embeddings = list(
        app_db_session.scalars(select(AppPassageEmbedding).where(AppPassageEmbedding.publication_id == publication_id))
    )
    remaining_contexts = list(
        app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == publication_id))
    )
    assert remaining_embeddings == []
    assert remaining_contexts == []


def test_audit_rows_for_embeddings_and_contexts(db_session, app_db_session):
    from market_documents.publishing import audit

    _build_and_feature(db_session, ticker="RET8")
    builder = PublicationBuilder(publication_version="ret-test-v8")
    publication = builder.build(db_session, app_db_session)
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason

    embedding_rows = audit.build_publication_embedding_audit_rows(app_db_session, publication.id)
    assert len(embedding_rows) == 2
    assert all(row.vector_is_nonzero for row in embedding_rows)

    lineage_rows = audit.build_publication_embedding_lineage_audit_rows(app_db_session, publication.id)
    assert len(lineage_rows) == 2

    missing_rows = audit.build_publication_embedding_missing_audit_rows(app_db_session, publication.id)
    assert missing_rows == []

    integrity_rows = audit.build_publication_vector_integrity_audit_rows(app_db_session, publication.id)
    assert all(row.dimensions_ok and row.vector_nonzero for row in integrity_rows)

    context_rows = audit.build_publication_retrieval_context_audit_rows(app_db_session, publication.id)
    assert len(context_rows) == 2

    duplicate_rows = audit.build_publication_retrieval_context_duplicate_audit_rows(app_db_session, publication.id)
    assert duplicate_rows == []
