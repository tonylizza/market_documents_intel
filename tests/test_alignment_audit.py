import math
from datetime import UTC, datetime

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
from market_documents.models.report_pair import ReportPair
from market_documents.services import passage_alignment as pa
from market_documents.services.alignment_audit import build_alignment_audit_rows
from market_documents.services.narrative_construction import compute_content_hash
from market_documents.services.review_sample import build_review_sample


def _vec(similarity_to_e0: float, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    theta = math.acos(max(-1.0, min(1.0, similarity_to_e0)))
    v = [0.0] * dim
    v[0] = math.cos(theta)
    v[1] = math.sin(theta)
    return v


BASE_VEC = _vec(1.0)


def _setup_and_align(db_session, ticker="AUD", gap_months=12, is_transition=False):
    company = Company(ticker=ticker, company_name="Alignment Audit Test Co")
    db_session.add(company)
    db_session.flush()

    def _report(suffix, year):
        report = Report(
            company_id=company.id, local_path=f"data/raw/{ticker}/{year}/{suffix}.pdf",
            filename=f"{suffix}.pdf", sha256=compute_content_hash(f"{ticker}-{suffix}"),
            directory_year=year, metadata_status=MetadataStatus.VALIDATED,
        )
        db_session.add(report)
        db_session.flush()
        return report

    earlier_report = _report("earlier", 2022)
    later_report = _report("later", 2023)

    def _extraction(report):
        run = ExtractionRun(
            report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="test-hash",
            status=ExtractionStatus.COMPLETED, extraction_quality=ExtractionQuality.GOOD,
            started_at=datetime.now(UTC), completed_at=datetime.now(UTC), encrypted_pdf_handled=False,
        )
        db_session.add(run)
        db_session.flush()
        return run

    earlier_extraction = _extraction(earlier_report)
    later_extraction = _extraction(later_report)

    def _narrative(run, report):
        doc = NarrativeDocument(
            extraction_run_id=run.id, report_id=report.id, cleaned_text="text",
            word_count=1, content_hash=compute_content_hash(f"narrative-{run.id}"),
        )
        db_session.add(doc)
        db_session.flush()
        return doc

    earlier_narrative = _narrative(earlier_extraction, earlier_report)
    later_narrative = _narrative(later_extraction, later_report)

    def _seg(narrative, run):
        seg = PassageSegmentationRun(
            narrative_document_id=narrative.id, extraction_run_id=run.id,
            algorithm_version="1.0.0", configuration_hash="seg-hash",
            status=PassageSegmentationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
        )
        db_session.add(seg)
        db_session.flush()
        return seg

    earlier_seg = _seg(earlier_narrative, earlier_extraction)
    later_seg = _seg(later_narrative, later_extraction)

    def _emb(seg):
        run = EmbeddingRun(
            segmentation_run_id=seg.id, model_name="test-model", model_revision="rev1",
            tokenizer_name="test-model", tokenizer_revision="rev1", embedding_dimension=EMBEDDING_DIMENSION,
            pooling_strategy="cls", normalization_method="l2", maximum_model_tokens=512,
            configuration_hash="emb-hash", status=EmbeddingRunStatus.COMPLETED, completed_at=datetime.now(UTC),
        )
        db_session.add(run)
        db_session.flush()
        return run

    earlier_emb = _emb(earlier_seg)
    later_emb = _emb(later_seg)

    def _passage(seg, report, index, text):
        passage = Passage(
            segmentation_run_id=seg.id, narrative_document_id=seg.narrative_document_id, report_id=report.id,
            extraction_run_id=seg.extraction_run_id, passage_index=index, raw_text=text, normalized_text=text.lower(),
            content_hash=compute_content_hash(f"{text}-{index}-{seg.id}"), first_page_number=1, last_page_number=1,
            word_count=len(text.split()), token_count=len(text.split()), character_count=len(text),
            heading_text=None, passage_type=PassageType.PARAGRAPH, excluded_from_alignment=False,
        )
        db_session.add(passage)
        db_session.flush()
        return passage

    def _embed(run, passage, vector):
        e = PassageEmbedding(embedding_run_id=run.id, passage_id=passage.id, embedding=vector, input_token_count=5, truncated=False)
        db_session.add(e)
        db_session.flush()
        return e

    text = "a well matched passage shared across both reports"
    e = _passage(earlier_seg, earlier_report, 0, text)
    l = _passage(later_seg, later_report, 0, text)
    _embed(earlier_emb, e, BASE_VEC)
    _embed(later_emb, l, BASE_VEC)

    pair = ReportPair(
        company_id=company.id, earlier_report_id=earlier_report.id, later_report_id=later_report.id,
        gap_months=gap_months, is_transition=is_transition,
    )
    db_session.add(pair)
    db_session.flush()

    outcome = pa.align_pair(db_session, pair)
    return pair, outcome


def test_audit_row_for_aligned_pair(db_session):
    pair, outcome = _setup_and_align(db_session, ticker="AUD1")

    rows = build_alignment_audit_rows(db_session)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))

    assert row.matched_count == 1
    assert row.unchanged_count == 1
    assert row.high_confidence_count == 1
    assert row.status == "COMPLETED"
    assert row.mean_semantic_similarity is not None


def test_audit_row_for_unaligned_pair(db_session):
    company = Company(ticker="NOALIGN", company_name="No Align Co")
    db_session.add(company)
    db_session.flush()
    earlier = Report(
        company_id=company.id, local_path="data/raw/NOALIGN/2022/earlier.pdf", filename="earlier.pdf",
        sha256=compute_content_hash("noalign-earlier"), directory_year=2022, metadata_status=MetadataStatus.VALIDATED,
    )
    later = Report(
        company_id=company.id, local_path="data/raw/NOALIGN/2023/later.pdf", filename="later.pdf",
        sha256=compute_content_hash("noalign-later"), directory_year=2023, metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add_all([earlier, later])
    db_session.flush()
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id, gap_months=12, is_transition=False)
    db_session.add(pair)
    db_session.flush()

    rows = build_alignment_audit_rows(db_session)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))
    assert row.status is None
    assert row.matched_count is None


def test_review_sample_includes_unchanged_category_without_text_by_default(db_session):
    _setup_and_align(db_session, ticker="RSAMP")
    rows = build_review_sample(db_session, per_category=5)
    unchanged_rows = [r for r in rows if r.category == "high_confidence_unchanged"]
    assert len(unchanged_rows) == 1
    assert unchanged_rows[0].earlier_text is None
    assert unchanged_rows[0].later_text is None


def test_review_sample_includes_text_only_when_requested(db_session):
    _setup_and_align(db_session, ticker="RSAMP2")
    rows = build_review_sample(db_session, per_category=5, include_text=True)
    unchanged_rows = [r for r in rows if r.category == "high_confidence_unchanged"]
    assert unchanged_rows[0].earlier_text is not None


def test_review_sample_is_deterministic_for_same_seed(db_session):
    _setup_and_align(db_session, ticker="RSAMP3")
    first = build_review_sample(db_session, seed=7, per_category=5)
    second = build_review_sample(db_session, seed=7, per_category=5)
    assert [r.category for r in first] == [r.category for r in second]
    assert [r.later_passage_id for r in first] == [r.later_passage_id for r in second]


def test_review_sample_includes_irregular_gap_category(db_session):
    _setup_and_align(db_session, ticker="RSAMP4", gap_months=96)
    rows = build_review_sample(db_session, per_category=5)
    assert any(r.category == "irregular_gap_pair" for r in rows)
