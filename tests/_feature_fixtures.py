"""Shared fixture-building helpers for Milestone 5 feature tests.

Not a test module itself (no `test_` prefix) -- builds a full, minimal
Company -> Report -> ExtractionRun -> NarrativeDocument -> Segmentation ->
Embedding -> Alignment -> Similarity chain so `build_features` has real
current successful similarity and alignment runs to select, mirroring the
per-file fixture-building style already used by `test_alignment_audit.py`.
"""

import math
from datetime import UTC, datetime

from market_documents.models.alignment import AlignmentRun, PassageAlignment
from market_documents.models.company import Company
from market_documents.models.embedding import EMBEDDING_DIMENSION, EmbeddingRun, PassageEmbedding
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentRunStatus,
    AlignmentStatus,
    AlignmentType,
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
from market_documents.services.narrative_construction import compute_content_hash
from market_documents.services.similarity import score_pair


def _vec(similarity_to_e0: float, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    theta = math.acos(max(-1.0, min(1.0, similarity_to_e0)))
    v = [0.0] * dim
    v[0] = math.cos(theta)
    v[1] = math.sin(theta)
    return v


BASE_VEC = _vec(1.0)

# 250 distinct tokens -- clears M3's min_words_for_review (200) on both
# sides so document-level similarity quality is GOOD by default.
_LONG_TEXT = " ".join(f"disclosure{i}" for i in range(250))


def build_ready_pair(
    db_session,
    *,
    ticker: str,
    gap_months: int = 12,
    is_transition: bool = False,
    earlier_text: str = _LONG_TEXT,
    later_text: str = _LONG_TEXT,
    extra_passages: list[tuple[str, str, int, str]] | None = None,
):
    """Build a ReportPair with a current successful SimilarityRun and
    AlignmentRun, ready for `build_features`.

    `extra_passages` is an optional list of `(side, text, index, passage_type)`
    tuples ("earlier" or "later") appended to the default single matched
    passage on each side, for tests that need NEW/REMOVED/short passages.
    Returns `(pair, alignment_outcome, similarity_outcome)`.
    """
    company = Company(ticker=ticker, company_name=f"{ticker} Feature Test Co")
    db_session.add(company)
    db_session.flush()

    def _report(suffix: str, year: int) -> Report:
        report = Report(
            company_id=company.id,
            local_path=f"data/raw/{ticker}/{year}/{suffix}.pdf",
            filename=f"{suffix}.pdf",
            sha256=compute_content_hash(f"{ticker}-{suffix}"),
            directory_year=year,
            metadata_status=MetadataStatus.VALIDATED,
        )
        db_session.add(report)
        db_session.flush()
        return report

    earlier_report = _report("earlier", 2022)
    later_report = _report("later", 2023)

    def _extraction(report: Report) -> ExtractionRun:
        run = ExtractionRun(
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
        db_session.add(run)
        db_session.flush()
        return run

    earlier_extraction = _extraction(earlier_report)
    later_extraction = _extraction(later_report)

    def _narrative(run: ExtractionRun, report: Report, text: str) -> NarrativeDocument:
        doc = NarrativeDocument(
            extraction_run_id=run.id,
            report_id=report.id,
            cleaned_text=text,
            word_count=len(text.split()),
            content_hash=compute_content_hash(f"narrative-{run.id}"),
        )
        db_session.add(doc)
        db_session.flush()
        return doc

    earlier_narrative = _narrative(earlier_extraction, earlier_report, earlier_text)
    later_narrative = _narrative(later_extraction, later_report, later_text)

    def _seg(narrative: NarrativeDocument, run: ExtractionRun) -> PassageSegmentationRun:
        seg = PassageSegmentationRun(
            narrative_document_id=narrative.id,
            extraction_run_id=run.id,
            algorithm_version="1.0.0",
            configuration_hash="seg-hash",
            status=PassageSegmentationRunStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        db_session.add(seg)
        db_session.flush()
        return seg

    earlier_seg = _seg(earlier_narrative, earlier_extraction)
    later_seg = _seg(later_narrative, later_extraction)

    def _emb(seg: PassageSegmentationRun) -> EmbeddingRun:
        run = EmbeddingRun(
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
        db_session.add(run)
        db_session.flush()
        return run

    earlier_emb = _emb(earlier_seg)
    later_emb = _emb(later_seg)

    def _passage(seg: PassageSegmentationRun, report: Report, index: int, text: str, ptype: PassageType) -> Passage:
        passage = Passage(
            segmentation_run_id=seg.id,
            narrative_document_id=seg.narrative_document_id,
            report_id=report.id,
            extraction_run_id=seg.extraction_run_id,
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
            passage_type=ptype,
            excluded_from_alignment=False,
        )
        db_session.add(passage)
        db_session.flush()
        return passage

    def _embed(run: EmbeddingRun, passage: Passage, vector: list[float]) -> None:
        db_session.add(
            PassageEmbedding(
                embedding_run_id=run.id, passage_id=passage.id, embedding=vector, input_token_count=5, truncated=False
            )
        )
        db_session.flush()
        run.embedded_passage_count = (run.embedded_passage_count or 0) + 1

    # 45 words -- clears the default 40-word feature-eligibility floor
    # (FeatureConfig.minimum_feature_passage_words) so a "clean" fixture
    # pair is feature-eligible by default, not silently excluded.
    base_text = " ".join(["matched"] * 45)
    earlier_index = 0
    later_index = 0
    e0 = _passage(earlier_seg, earlier_report, earlier_index, base_text, PassageType.PARAGRAPH)
    l0 = _passage(later_seg, later_report, later_index, base_text, PassageType.PARAGRAPH)
    _embed(earlier_emb, e0, BASE_VEC)
    _embed(later_emb, l0, BASE_VEC)
    earlier_index += 1
    later_index += 1

    for side, text, _unused_index, ptype_name in extra_passages or []:
        ptype = PassageType[ptype_name]
        if side == "earlier":
            p = _passage(earlier_seg, earlier_report, earlier_index, text, ptype)
            _embed(earlier_emb, p, _vec(0.9))
            earlier_index += 1
        else:
            p = _passage(later_seg, later_report, later_index, text, ptype)
            _embed(later_emb, p, _vec(0.9))
            later_index += 1

    db_session.flush()

    pair = ReportPair(
        company_id=company.id,
        earlier_report_id=earlier_report.id,
        later_report_id=later_report.id,
        gap_months=gap_months,
        is_transition=is_transition,
    )
    db_session.add(pair)
    db_session.flush()

    alignment_outcome = pa.align_pair(db_session, pair)
    similarity_outcome = score_pair(db_session, pair)
    db_session.flush()

    return pair, alignment_outcome, similarity_outcome


def build_manual_alignment_pair(
    db_session,
    *,
    ticker: str,
    gap_months: int = 12,
    is_transition: bool = False,
    earlier_texts: list[tuple[str, PassageType]],
    later_texts: list[tuple[str, PassageType]],
    rows: list[dict],
    earlier_text: str = _LONG_TEXT,
    later_text: str = _LONG_TEXT,
):
    """Build a ReportPair with a hand-specified `AlignmentRun`/`PassageAlignment`
    population, bypassing the real alignment algorithm entirely.

    `rows` is a list of dicts, each with keys `earlier` (index into
    `earlier_texts` or `None`), `later` (index into `later_texts` or
    `None`), `status` (`AlignmentStatus`), and `confidence`
    (`AlignmentConfidence`) -- lets a test assert exact, hand-computed
    feature values against a fully known population, directly exercising
    "exact reproducibility from PassageAlignment rows".
    """
    company = Company(ticker=ticker, company_name=f"{ticker} Feature Test Co")
    db_session.add(company)
    db_session.flush()

    def _report(suffix: str, year: int) -> Report:
        report = Report(
            company_id=company.id,
            local_path=f"data/raw/{ticker}/{year}/{suffix}.pdf",
            filename=f"{suffix}.pdf",
            sha256=compute_content_hash(f"{ticker}-{suffix}"),
            directory_year=year,
            metadata_status=MetadataStatus.VALIDATED,
        )
        db_session.add(report)
        db_session.flush()
        return report

    earlier_report = _report("earlier", 2022)
    later_report = _report("later", 2023)

    def _extraction(report: Report) -> ExtractionRun:
        run = ExtractionRun(
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
        db_session.add(run)
        db_session.flush()
        return run

    earlier_extraction = _extraction(earlier_report)
    later_extraction = _extraction(later_report)

    def _narrative(run: ExtractionRun, report: Report, text: str) -> NarrativeDocument:
        doc = NarrativeDocument(
            extraction_run_id=run.id,
            report_id=report.id,
            cleaned_text=text,
            word_count=len(text.split()),
            content_hash=compute_content_hash(f"narrative-{run.id}"),
        )
        db_session.add(doc)
        db_session.flush()
        return doc

    earlier_narrative = _narrative(earlier_extraction, earlier_report, earlier_text)
    later_narrative = _narrative(later_extraction, later_report, later_text)

    def _seg(narrative: NarrativeDocument, run: ExtractionRun) -> PassageSegmentationRun:
        seg = PassageSegmentationRun(
            narrative_document_id=narrative.id,
            extraction_run_id=run.id,
            algorithm_version="1.0.0",
            configuration_hash="seg-hash",
            status=PassageSegmentationRunStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        db_session.add(seg)
        db_session.flush()
        return seg

    earlier_seg = _seg(earlier_narrative, earlier_extraction)
    later_seg = _seg(later_narrative, later_extraction)

    def _emb(seg: PassageSegmentationRun, embedded: int, skipped: int) -> EmbeddingRun:
        run = EmbeddingRun(
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
            embedded_passage_count=embedded,
            skipped_passage_count=skipped,
        )
        db_session.add(run)
        db_session.flush()
        return run

    earlier_emb = _emb(earlier_seg, embedded=len(earlier_texts), skipped=0)
    later_emb = _emb(later_seg, embedded=len(later_texts), skipped=0)

    def _passage(seg: PassageSegmentationRun, report: Report, index: int, text: str, ptype: PassageType) -> Passage:
        passage = Passage(
            segmentation_run_id=seg.id,
            narrative_document_id=seg.narrative_document_id,
            report_id=report.id,
            extraction_run_id=seg.extraction_run_id,
            passage_index=index,
            raw_text=text,
            normalized_text=text.lower(),
            content_hash=compute_content_hash(f"{text}-{index}-{seg.id}"),
            first_page_number=1,
            last_page_number=1,
            word_count=len(text.split()),
            token_count=len(text.split()),
            character_count=len(text),
            heading_text="H" if ptype == PassageType.HEADING_WITH_BODY else None,
            passage_type=ptype,
            excluded_from_alignment=False,
        )
        db_session.add(passage)
        db_session.flush()
        return passage

    earlier_passages = [
        _passage(earlier_seg, earlier_report, i, text, ptype) for i, (text, ptype) in enumerate(earlier_texts)
    ]
    later_passages = [
        _passage(later_seg, later_report, i, text, ptype) for i, (text, ptype) in enumerate(later_texts)
    ]

    pair = ReportPair(
        company_id=company.id,
        earlier_report_id=earlier_report.id,
        later_report_id=later_report.id,
        gap_months=gap_months,
        is_transition=is_transition,
    )
    db_session.add(pair)
    db_session.flush()

    alignment_run = AlignmentRun(
        report_pair_id=pair.id,
        earlier_segmentation_run_id=earlier_seg.id,
        later_segmentation_run_id=later_seg.id,
        earlier_embedding_run_id=earlier_emb.id,
        later_embedding_run_id=later_emb.id,
        algorithm_version="1.0.0",
        configuration_hash="manual-alignment-hash",
        status=AlignmentRunStatus.COMPLETED,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db_session.add(alignment_run)
    db_session.flush()

    for spec in rows:
        earlier_idx = spec.get("earlier")
        later_idx = spec.get("later")
        status: AlignmentStatus = spec["status"]
        confidence: AlignmentConfidence = spec["confidence"]
        if earlier_idx is not None and later_idx is not None:
            alignment_type = AlignmentType.ONE_TO_ONE
        elif earlier_idx is not None:
            alignment_type = AlignmentType.UNMATCHED_EARLIER
        else:
            alignment_type = AlignmentType.UNMATCHED_LATER
        db_session.add(
            PassageAlignment(
                alignment_run_id=alignment_run.id,
                report_pair_id=pair.id,
                earlier_passage_id=earlier_passages[earlier_idx].id if earlier_idx is not None else None,
                later_passage_id=later_passages[later_idx].id if later_idx is not None else None,
                alignment_status=status,
                alignment_type=alignment_type,
                confidence=confidence,
                primary_alignment=True,
            )
        )
    db_session.flush()

    similarity_outcome = score_pair(db_session, pair)
    db_session.flush()

    return pair, alignment_run, earlier_passages, later_passages, similarity_outcome
