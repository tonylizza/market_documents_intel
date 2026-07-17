from datetime import UTC, datetime

from market_documents.models.company import Company
from market_documents.models.enums import (
    BlockType,
    EmbeddingRunStatus,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    PassageSegmentationRunStatus,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument, Page, TextBlock
from market_documents.models.passage import PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.services import passage_embedding as pe
from market_documents.services import passage_segmentation as ps
from market_documents.services.embedding_config import EMBEDDING_DIMENSION
from market_documents.services.narrative_construction import build_narrative_text, compute_content_hash


class FakeEmbeddingModel:
    """Deterministic in-memory stand-in for the real sentence-transformers
    model, so orchestration/batching tests never touch the network or a
    real model."""

    def __init__(self, *, fail_for=None, wrong_dim_for=None, token_counts=None):
        self.fail_for = fail_for or set()
        self.wrong_dim_for = wrong_dim_for or set()
        self.token_counts = token_counts or {}

    def count_tokens(self, text: str) -> int:
        return self.token_counts.get(text, len(text.split()))

    def encode_batch(self, texts: list[str]) -> list[pe.EncodedPassage]:
        results = []
        for text in texts:
            if text in self.fail_for:
                raise RuntimeError(f"fake failure for {text!r}")
            dim = 1 if text in self.wrong_dim_for else EMBEDDING_DIMENSION
            results.append(
                pe.EncodedPassage(vector=[0.1] * dim, input_token_count=self.count_tokens(text), truncated=False)
            )
        return results


def _words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def _company(db_session, ticker="EMB") -> Company:
    company = Company(ticker=ticker, company_name="Embedding Test Co")
    db_session.add(company)
    db_session.flush()
    return company


def _report(db_session, company: Company, year: int, path_suffix: str) -> Report:
    local_path = f"data/raw/{company.ticker}/{year}/{path_suffix}.pdf"
    report = Report(
        company_id=company.id,
        local_path=local_path,
        filename=f"{path_suffix}.pdf",
        sha256=compute_content_hash(local_path),
        directory_year=year,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()
    return report


def _segmented_run(db_session, ticker="EMB") -> PassageSegmentationRun:
    """A real segmentation run with two eligible passages, via the actual
    segmentation service (not hand-built rows)."""
    company = _company(db_session, ticker)
    report = _report(db_session, company, 2023, "annual")
    extraction_run = ExtractionRun(
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
    db_session.add(extraction_run)
    db_session.flush()

    page = Page(
        extraction_run_id=extraction_run.id,
        report_id=report.id,
        page_number=1,
        raw_text="text",
        cleaned_text="text",
        character_count=4,
        word_count=1,
        block_count=2,
        native_text_available=True,
        suspected_image_only=False,
        extraction_quality=ExtractionQuality.GOOD,
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
            block_index=1, reading_order=1, raw_text=_words(80), cleaned_text=_words(80),
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

    outcome = ps.segment_report(db_session, report)
    assert outcome.run is not None
    return outcome.run


def test_embed_ineligible_segmentation_run_not_successful(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2023, "annual")
    run = PassageSegmentationRun(
        narrative_document_id=report.id,  # not a real narrative FK target, but run never gets flushed as FAILED-eligible path
        extraction_run_id=report.id,
        algorithm_version="1.0.0",
        configuration_hash="hash",
        status=PassageSegmentationRunStatus.FAILED,
    )
    outcome = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel())
    assert outcome.ineligible
    assert "not successful" in outcome.ineligible_reason


def test_embed_success_persists_embeddings(db_session):
    run = _segmented_run(db_session)
    outcome = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel())

    assert outcome.run is not None
    assert outcome.run.status == EmbeddingRunStatus.COMPLETED
    assert outcome.run.embedded_passage_count == run.passage_count - (run.excluded_passage_count or 0)
    assert outcome.run.skipped_passage_count == 0

    embeddings = db_session.query(pe.PassageEmbedding).filter_by(embedding_run_id=outcome.run.id).all()
    assert len(embeddings) == outcome.run.embedded_passage_count
    assert all(len(e.embedding) == EMBEDDING_DIMENSION for e in embeddings)


def test_embed_skips_identical_successful_run(db_session):
    run = _segmented_run(db_session)
    first = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel())
    second = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel())
    assert second.skipped
    assert second.run.id == first.run.id


def test_embed_force_reruns(db_session):
    run = _segmented_run(db_session)
    first = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel())
    second = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel(), force=True)
    assert not second.skipped
    assert second.run.id != first.run.id


def test_embed_configuration_change_triggers_new_run(db_session, monkeypatch):
    run = _segmented_run(db_session)
    first = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel())

    from market_documents.services import embedding_config

    monkeypatch.setattr(embedding_config, "EMBEDDING_CONFIG_VERSION", 999)
    second = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel())
    assert not second.skipped
    assert second.run.configuration_hash != first.run.configuration_hash


def test_oversized_passage_is_skipped_not_truncated(db_session):
    run = _segmented_run(db_session)
    passages = db_session.query(pe.Passage).filter_by(segmentation_run_id=run.id).all()
    oversized_text = next(p.raw_text for p in passages if not p.excluded_from_alignment)

    model = FakeEmbeddingModel(token_counts={oversized_text: 9999})
    outcome = pe.embed_segmentation_run(db_session, run, model=model)

    assert outcome.run.status == EmbeddingRunStatus.COMPLETED_WITH_WARNINGS
    assert outcome.run.skipped_passage_count >= 1
    assert "exceeds model limit" in outcome.run.review_reason
    assert "truncated" not in outcome.run.review_reason.split("skipped")[0]


def test_per_passage_embedding_failure_is_isolated(db_session):
    run = _segmented_run(db_session)
    passages = db_session.query(pe.Passage).filter_by(segmentation_run_id=run.id).all()
    eligible_texts = [p.raw_text for p in passages if not p.excluded_from_alignment]
    assert len(eligible_texts) >= 1
    failing_text = eligible_texts[0]

    model = FakeEmbeddingModel(fail_for={failing_text})
    outcome = pe.embed_segmentation_run(db_session, run, model=model)

    assert outcome.run.status == EmbeddingRunStatus.COMPLETED_WITH_WARNINGS
    assert outcome.run.skipped_passage_count >= 1
    assert outcome.run.embedded_passage_count == len(eligible_texts) - 1


def test_wrong_dimension_embedding_is_rejected(db_session):
    run = _segmented_run(db_session)
    passages = db_session.query(pe.Passage).filter_by(segmentation_run_id=run.id).all()
    eligible_texts = [p.raw_text for p in passages if not p.excluded_from_alignment]
    bad_text = eligible_texts[0]

    model = FakeEmbeddingModel(wrong_dim_for={bad_text})
    outcome = pe.embed_segmentation_run(db_session, run, model=model)

    assert outcome.run.status == EmbeddingRunStatus.COMPLETED_WITH_WARNINGS
    assert any("dimension" in w for w in (outcome.run.review_reason or "").split("; "))


def test_batching_respects_batch_size(db_session):
    run = _segmented_run(db_session)
    outcome = pe.embed_segmentation_run(db_session, run, model=FakeEmbeddingModel(), batch_size=1)
    assert outcome.run.status == EmbeddingRunStatus.COMPLETED
    embeddings = db_session.query(pe.PassageEmbedding).filter_by(embedding_run_id=outcome.run.id).all()
    assert len(embeddings) == outcome.run.embedded_passage_count
