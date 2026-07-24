"""Oversized-passage audit: which passages were skipped from embedding for
exceeding the token limit (not any other skip reason), their alignment-gap
participation, and stable CSV output.

Mirrors `test_passage_embedding.py`'s `FakeEmbeddingModel` fixture and
`test_vector_index.py`'s hand-built Passage fixtures (full control over
`raw_text`/`word_count`, rather than depending on the real segmentation
algorithm's output count).
"""

import csv
from datetime import UTC, datetime

from market_documents.models.alignment import AlignmentRun, PassageAlignment
from market_documents.models.company import Company
from market_documents.models.embedding import EMBEDDING_DIMENSION
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentRunStatus,
    AlignmentStatus,
    AlignmentType,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    PassageSegmentationRunStatus,
    PassageType,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.services import passage_embedding as pe
from market_documents.services.embedding_config import MAXIMUM_MODEL_TOKENS
from market_documents.services.narrative_construction import compute_content_hash
from market_documents.services.oversized_passage_audit import (
    build_oversized_passage_audit_rows,
    write_oversized_passage_audit_csv,
)


class FakeTokenizerModel:
    """Reports a fixed token count per exact text, mirroring
    `test_passage_embedding.py`'s `FakeEmbeddingModel` but usable both as
    the embedding orchestration model and as the audit's recomputation
    tokenizer."""

    def __init__(self, token_counts: dict[str, int]):
        self.token_counts = token_counts

    def count_tokens(self, text: str) -> int:
        return self.token_counts.get(text, len(text.split()))

    def encode_batch(self, texts: list[str]) -> list[pe.EncodedPassage]:
        return [
            pe.EncodedPassage(vector=[0.1] * EMBEDDING_DIMENSION, input_token_count=self.count_tokens(t), truncated=False)
            for t in texts
        ]


def _report_with_narrative(db_session, ticker: str, *, narrative_word_count: int = 1000) -> tuple[Report, NarrativeDocument]:
    company = Company(ticker=ticker, company_name="Oversized Audit Test Co")
    db_session.add(company)
    db_session.flush()
    report = Report(
        company_id=company.id, local_path=f"data/raw/{ticker}/2023/annual.pdf", filename="annual.pdf",
        sha256=compute_content_hash(ticker), directory_year=2023, metadata_status=MetadataStatus.VALIDATED,
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
        word_count=narrative_word_count, content_hash=compute_content_hash(f"{ticker}-text"),
    )
    db_session.add(narrative)
    db_session.flush()
    return report, narrative


def _segmentation_run(db_session, narrative: NarrativeDocument) -> PassageSegmentationRun:
    segmentation_run = PassageSegmentationRun(
        narrative_document_id=narrative.id, extraction_run_id=narrative.extraction_run_id,
        algorithm_version="1.0.0", configuration_hash="seg-hash",
        status=PassageSegmentationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    db_session.add(segmentation_run)
    db_session.flush()
    return segmentation_run


def _passage(db_session, segmentation_run, report, *, index: int, raw_text: str, word_count: int) -> Passage:
    passage = Passage(
        segmentation_run_id=segmentation_run.id, narrative_document_id=segmentation_run.narrative_document_id,
        report_id=report.id, extraction_run_id=segmentation_run.extraction_run_id, passage_index=index,
        raw_text=raw_text, normalized_text=raw_text, content_hash=compute_content_hash(f"{report.id}-{index}"),
        first_page_number=index + 1, last_page_number=index + 1, word_count=word_count, token_count=word_count,
        character_count=len(raw_text), passage_type=PassageType.PARAGRAPH, excluded_from_alignment=False,
    )
    db_session.add(passage)
    db_session.flush()
    return passage


def test_oversized_skipped_passage_appears_with_expected_fields(db_session):
    report, narrative = _report_with_narrative(db_session, "OVR1", narrative_word_count=1000)
    segmentation_run = _segmentation_run(db_session, narrative)
    oversized_text = "oversized passage text"
    normal_text = "normal passage text"
    p_oversized = _passage(db_session, segmentation_run, report, index=0, raw_text=oversized_text, word_count=400)
    _passage(db_session, segmentation_run, report, index=1, raw_text=normal_text, word_count=50)

    model = FakeTokenizerModel({oversized_text: MAXIMUM_MODEL_TOKENS + 50, normal_text: 100})
    outcome = pe.embed_segmentation_run(db_session, segmentation_run, model=model)
    assert outcome.run.skipped_passage_count == 1

    rows = build_oversized_passage_audit_rows(db_session, model)
    assert len(rows) == 1
    row = rows[0]
    assert row.passage_id == str(p_oversized.id)
    assert row.ticker == "OVR1"
    assert row.token_count == MAXIMUM_MODEL_TOKENS + 50
    assert row.word_count == 400
    assert row.share_of_report_words == 400 / 1000
    assert row.participates_in_alignment_gap is None  # no alignment run covers this side yet
    assert row.cumulative_corpus_word_share > 0.0


def test_passage_skipped_for_other_reasons_is_excluded_from_oversized_audit(db_session):
    report, narrative = _report_with_narrative(db_session, "OVR2")
    segmentation_run = _segmentation_run(db_session, narrative)
    failing_text = "this passage fails to embed"
    _passage(db_session, segmentation_run, report, index=0, raw_text=failing_text, word_count=10)

    class FailingModel(FakeTokenizerModel):
        def encode_batch(self, texts):
            raise RuntimeError("boom")

    model = FailingModel({failing_text: 10})
    outcome = pe.embed_segmentation_run(db_session, segmentation_run, model=model)
    assert outcome.run.skipped_passage_count == 1

    rows = build_oversized_passage_audit_rows(db_session, model)
    assert rows == []  # token count (10) is under the limit -- not a size issue


def test_oversized_passage_participates_in_alignment_gap_when_covered_by_alignment_run(db_session):
    report, narrative = _report_with_narrative(db_session, "OVR3")
    segmentation_run = _segmentation_run(db_session, narrative)
    oversized_text = "oversized passage for gap test"
    p_oversized = _passage(db_session, segmentation_run, report, index=0, raw_text=oversized_text, word_count=400)

    model = FakeTokenizerModel({oversized_text: MAXIMUM_MODEL_TOKENS + 1})
    outcome = pe.embed_segmentation_run(db_session, segmentation_run, model=model)
    embedding_run = outcome.run

    from market_documents.models.report_pair import ReportPair

    later_report, later_narrative = _report_with_narrative(db_session, "OVR3L")
    later_segmentation_run = _segmentation_run(db_session, later_narrative)
    pair = ReportPair(
        company_id=report.company_id, earlier_report_id=report.id, later_report_id=later_report.id, gap_months=12,
    )
    db_session.add(pair)
    db_session.flush()

    alignment_run = AlignmentRun(
        report_pair_id=pair.id, earlier_segmentation_run_id=segmentation_run.id,
        later_segmentation_run_id=later_segmentation_run.id, earlier_embedding_run_id=embedding_run.id,
        later_embedding_run_id=embedding_run.id, algorithm_version="1.0.0", configuration_hash="align-hash",
        status=AlignmentRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    db_session.add(alignment_run)
    db_session.flush()
    db_session.add(
        PassageAlignment(
            alignment_run_id=alignment_run.id, report_pair_id=pair.id, earlier_passage_id=p_oversized.id,
            later_passage_id=None, alignment_status=AlignmentStatus.REMOVED,
            alignment_type=AlignmentType.UNMATCHED_EARLIER, confidence=AlignmentConfidence.HIGH,
        )
    )
    db_session.flush()

    rows = build_oversized_passage_audit_rows(db_session, model)
    assert len(rows) == 1
    assert rows[0].participates_in_alignment_gap is True


def test_write_oversized_passage_audit_csv_is_stable(db_session, tmp_path):
    report, narrative = _report_with_narrative(db_session, "OVR4")
    segmentation_run = _segmentation_run(db_session, narrative)
    oversized_text = "oversized passage for csv stability"
    _passage(db_session, segmentation_run, report, index=0, raw_text=oversized_text, word_count=400)
    model = FakeTokenizerModel({oversized_text: MAXIMUM_MODEL_TOKENS + 1})
    pe.embed_segmentation_run(db_session, segmentation_run, model=model)

    rows = build_oversized_passage_audit_rows(db_session, model)
    output_path = tmp_path / "oversized_passage_audit.csv"
    write_oversized_passage_audit_csv(rows, output_path)
    first_bytes = output_path.read_bytes()

    write_oversized_passage_audit_csv(rows, output_path)
    second_bytes = output_path.read_bytes()
    assert first_bytes == second_bytes

    with output_path.open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == [
            "ticker", "report_id", "passage_id", "passage_type", "first_page_number", "last_page_number",
            "word_count", "token_count", "share_of_report_words", "participates_in_alignment_gap",
            "cumulative_corpus_word_share",
        ]
        written_rows = list(reader)
    assert len(written_rows) == 1
