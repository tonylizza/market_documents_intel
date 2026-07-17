from datetime import UTC, datetime

from market_documents.models.company import Company
from market_documents.models.enums import BlockType, ExtractionQuality, ExtractionStatus, MetadataStatus
from market_documents.models.extraction import ExtractionRun, NarrativeDocument, Page, TextBlock
from market_documents.models.report import Report
from market_documents.services import passage_embedding as pe
from market_documents.services import passage_segmentation as ps
from market_documents.services.embedding_audit import build_embedding_audit_rows
from market_documents.services.embedding_config import EMBEDDING_DIMENSION
from market_documents.services.narrative_construction import build_narrative_text, compute_content_hash


class FakeEmbeddingModel:
    """Deterministic in-memory stand-in for the real embedding model (see
    test_passage_embedding.py for the same fixture)."""

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def encode_batch(self, texts: list[str]) -> list[pe.EncodedPassage]:
        return [
            pe.EncodedPassage(vector=[0.1] * EMBEDDING_DIMENSION, input_token_count=self.count_tokens(text), truncated=False)
            for text in texts
        ]


def _words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def _segmented_report(db_session, ticker="EAUD"):
    company = Company(ticker=ticker, company_name="Embedding Audit Test Co")
    db_session.add(company)
    db_session.flush()

    report = Report(
        company_id=company.id,
        local_path=f"data/raw/{ticker}/2023/annual.pdf",
        filename="annual.pdf",
        sha256=compute_content_hash(f"{ticker}-annual"),
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

    return report


def test_audit_row_for_embedded_report(db_session):
    report = _segmented_report(db_session)
    seg_outcome = ps.segment_report(db_session, report)
    pe.embed_segmentation_run(db_session, seg_outcome.run, model=FakeEmbeddingModel())

    rows = build_embedding_audit_rows(db_session)
    row = next(r for r in rows if r.report_id == str(report.id))

    assert row.embedding_run_id is not None
    assert row.model_name == "BAAI/bge-small-en-v1.5"
    assert row.embedded_count == row.eligible_passage_count
    assert row.status == "COMPLETED"
    assert row.failed_count == 0
    assert row.truncated_count == 0


def test_audit_row_for_unembedded_but_segmented_report(db_session):
    report = _segmented_report(db_session)
    ps.segment_report(db_session, report)

    rows = build_embedding_audit_rows(db_session)
    row = next(r for r in rows if r.report_id == str(report.id))

    assert row.segmentation_run_id is not None
    assert row.embedding_run_id is None
    assert row.embedded_count is None
