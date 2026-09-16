"""Tests for Track 7C.5's `services.shadow_evaluation` -- a read-only
comparison of legacy passage-alignment output against the new
semantic-unit/structured-table pipeline output.

Builds minimal fixtures directly via the ORM (not through either
pipeline's service layer), mirroring the pattern in
`tests/_feature_fixtures.py` and `tests/test_analytical_eligibility_service.py`.
"""

from datetime import UTC, datetime
import hashlib

from sqlalchemy import select

from market_documents.models.alignment import AlignmentRun, PassageAlignment
from market_documents.models.company import Company
from market_documents.models.embedding import EmbeddingRun
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentMatchSource,
    AlignmentRunStatus,
    AlignmentStatus,
    AlignmentType,
    BoundaryConfidence,
    EmbeddingRunStatus,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    NormalizedSchedule,
    PassageSegmentationRunStatus,
    PassageType,
    ScheduleLocalizationRunStatus,
    ScheduleLocalizationStatus,
    SemanticUnitAlignmentRunStatus,
    SemanticUnitAlignmentStatus,
    SemanticUnitBoundaryStatus,
    SemanticUnitBoundaryStrategy,
    SemanticUnitRunStatus,
    SemanticUnitType,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.schedule import ScheduleInstance, ScheduleLocalizationRun
from market_documents.models.semantic_unit import SemanticUnit, SemanticUnitRun
from market_documents.models.semantic_unit_alignment import SemanticUnitAlignment, SemanticUnitAlignmentRun
from market_documents.services import shadow_evaluation as se

SCHEDULE = NormalizedSchedule.FINANCIAL_PERFORMANCE


def _company(session, ticker="BEL") -> Company:
    company = Company(ticker=ticker, company_name=f"{ticker} Shadow Eval Test")
    session.add(company)
    session.flush()
    return company


def _report(session, company, year, suffix="r") -> Report:
    report = Report(
        company_id=company.id,
        local_path=f"data/raw/{company.ticker}/{year}/{suffix}.pdf",
        filename=f"{suffix}.pdf",
        sha256=f"{company.ticker}-{suffix}-{year}",
        directory_year=year,
        metadata_status=MetadataStatus.VALIDATED,
    )
    session.add(report)
    session.flush()
    return report


def _extraction_run(session, report) -> ExtractionRun:
    run = ExtractionRun(
        report_id=report.id,
        extractor_name="test",
        extractor_version="1",
        configuration_hash="x",
        status=ExtractionStatus.COMPLETED,
        extraction_quality=ExtractionQuality.GOOD,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        encrypted_pdf_handled=False,
    )
    session.add(run)
    session.flush()
    return run


def _narrative(session, run, report, text="hello world") -> NarrativeDocument:
    doc = NarrativeDocument(
        extraction_run_id=run.id, report_id=report.id, cleaned_text=text, word_count=len(text.split()),
        content_hash=f"narrative-{run.id}",
    )
    session.add(doc)
    session.flush()
    return doc


def _seg_run(session, narrative, extraction_run) -> PassageSegmentationRun:
    seg = PassageSegmentationRun(
        narrative_document_id=narrative.id, extraction_run_id=extraction_run.id, algorithm_version="1",
        configuration_hash="x", status=PassageSegmentationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(seg)
    session.flush()
    return seg


def _passage(session, seg, report, index, text, ptype=PassageType.HEADING_WITH_BODY, excluded=False) -> Passage:
    passage = Passage(
        segmentation_run_id=seg.id, narrative_document_id=seg.narrative_document_id, report_id=report.id,
        extraction_run_id=seg.extraction_run_id, passage_index=index, raw_text=text, normalized_text=text.lower(),
        content_hash=hashlib.sha256(f"{text}-{index}-{seg.id}".encode()).hexdigest(), first_page_number=1, last_page_number=1,
        word_count=len(text.split()), token_count=len(text.split()), character_count=len(text),
        heading_text="H", passage_type=ptype, excluded_from_alignment=excluded,
    )
    session.add(passage)
    session.flush()
    return passage


def _embedding_run(session, seg, n) -> EmbeddingRun:
    run = EmbeddingRun(
        segmentation_run_id=seg.id, model_name="m", model_revision="r", tokenizer_name="m", tokenizer_revision="r",
        embedding_dimension=8, pooling_strategy="cls", normalization_method="l2", maximum_model_tokens=512,
        configuration_hash="x", status=EmbeddingRunStatus.COMPLETED, completed_at=datetime.now(UTC),
        embedded_passage_count=n, skipped_passage_count=0,
    )
    session.add(run)
    session.flush()
    return run


def _localization_run(session, report, extraction_run) -> ScheduleLocalizationRun:
    run = ScheduleLocalizationRun(
        report_id=report.id, extraction_run_id=extraction_run.id, schedule=SCHEDULE, algorithm_version="1",
        configuration_hash="x", status=ScheduleLocalizationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _schedule_instance(session, loc_run, report) -> ScheduleInstance:
    instance = ScheduleInstance(
        schedule_localization_run_id=loc_run.id, report_id=report.id, schedule=SCHEDULE,
        status=ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY, heading_text="Gross Margin", start_page=10,
        end_page=10, boundary_confidence=BoundaryConfidence.HIGH,
    )
    session.add(instance)
    session.flush()
    return instance


def _unit_run(session, report, loc_run, review_reason=None) -> SemanticUnitRun:
    run = SemanticUnitRun(
        report_id=report.id, schedule_localization_run_id=loc_run.id, schedule=SCHEDULE, algorithm_version="1",
        configuration_hash="x",
        status=SemanticUnitRunStatus.COMPLETED if review_reason is None else SemanticUnitRunStatus.COMPLETED_WITH_WARNINGS,
        completed_at=datetime.now(UTC), review_reason=review_reason,
    )
    session.add(run)
    session.flush()
    return run


def _unit(session, unit_run, report, instance, unit_key="gross_margin", word_count=20) -> SemanticUnit:
    unit = SemanticUnit(
        semantic_unit_run_id=unit_run.id, report_id=report.id, schedule_instance_id=instance.id, unit_key=unit_key,
        unit_type=SemanticUnitType.HEADED_NARRATIVE_UNIT, source_heading="Gross Margin", start_page=10,
        boundary_strategy=SemanticUnitBoundaryStrategy.ANCHOR_SENTENCE, boundary_status=SemanticUnitBoundaryStatus.RESOLVED,
        boundary_confidence=BoundaryConfidence.HIGH, end_page=10, source_text="text " * word_count,
        word_count=word_count,
    )
    session.add(unit)
    session.flush()
    return unit


# --- classify_difference (pure) -------------------------------------------------


def test_classify_difference_known_recall_defect_wins():
    result = se.classify_difference(SemanticUnitAlignmentStatus.MATCHED, known_new_pipeline_recall_defect=True)
    assert result == se.DifferenceClassification.NEW_PIPELINE_DEFECT


def test_classify_difference_matched_is_equivalent_result():
    result = se.classify_difference(SemanticUnitAlignmentStatus.MATCHED, known_new_pipeline_recall_defect=False)
    assert result == se.DifferenceClassification.EQUIVALENT_RESULT_DIFFERENT_BOUNDARY


def test_classify_difference_unresolved_upstream_is_architectural_improvement():
    result = se.classify_difference(SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, known_new_pipeline_recall_defect=False)
    assert result == se.DifferenceClassification.EXPECTED_ARCHITECTURAL_IMPROVEMENT


def test_classify_difference_other_status_is_inconclusive():
    result = se.classify_difference(SemanticUnitAlignmentStatus.AMBIGUOUS, known_new_pipeline_recall_defect=False)
    assert result == se.DifferenceClassification.INCONCLUSIVE


# --- legacy passage stats (DB-backed) --------------------------------------------


def test_compute_legacy_passage_stats_counts_short_passages(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2020)
    extraction = _extraction_run(db_session, report)
    narrative = _narrative(db_session, extraction, report)
    seg = _seg_run(db_session, narrative, extraction)
    _passage(db_session, seg, report, 0, "one two three")  # 3 words: short
    _passage(db_session, seg, report, 1, " ".join(["word"] * 30))  # 30 words: not short
    _passage(db_session, seg, report, 2, "excluded text here", excluded=True)

    stats = se.compute_legacy_passage_stats(db_session, report)

    assert stats.passage_count == 3
    assert stats.short_passage_count == 2  # "one two three" and the excluded 3-word passage
    assert stats.excluded_count == 1
    assert stats.short_passage_fraction == 2 / 3


def test_compute_legacy_passage_stats_empty_report(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2021)
    stats = se.compute_legacy_passage_stats(db_session, report)
    assert stats.passage_count == 0
    assert stats.short_passage_fraction is None


# --- legacy alignment stats (DB-backed) ------------------------------------------


def test_compute_legacy_alignment_stats_counts_statuses_and_confidence(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2020, "earlier")
    later_report = _report(db_session, company, 2021, "later")
    earlier_extraction = _extraction_run(db_session, earlier_report)
    later_extraction = _extraction_run(db_session, later_report)
    earlier_narrative = _narrative(db_session, earlier_extraction, earlier_report)
    later_narrative = _narrative(db_session, later_extraction, later_report)
    earlier_seg = _seg_run(db_session, earlier_narrative, earlier_extraction)
    later_seg = _seg_run(db_session, later_narrative, later_extraction)
    earlier_passage = _passage(db_session, earlier_seg, earlier_report, 0, "earlier text")
    later_passage = _passage(db_session, later_seg, later_report, 0, "later text")
    earlier_emb = _embedding_run(db_session, earlier_seg, 1)
    later_emb = _embedding_run(db_session, later_seg, 1)

    pair = ReportPair(company_id=company.id, earlier_report_id=earlier_report.id, later_report_id=later_report.id, gap_months=12)
    db_session.add(pair)
    db_session.flush()

    alignment_run = AlignmentRun(
        report_pair_id=pair.id, earlier_segmentation_run_id=earlier_seg.id, later_segmentation_run_id=later_seg.id,
        earlier_embedding_run_id=earlier_emb.id, later_embedding_run_id=later_emb.id, algorithm_version="1",
        configuration_hash="x", status=AlignmentRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    db_session.add(alignment_run)
    db_session.flush()
    db_session.add(
        PassageAlignment(
            alignment_run_id=alignment_run.id, report_pair_id=pair.id, earlier_passage_id=earlier_passage.id,
            later_passage_id=later_passage.id, alignment_status=AlignmentStatus.UNCHANGED,
            alignment_type=AlignmentType.ONE_TO_ONE, confidence=AlignmentConfidence.NEEDS_REVIEW,
            primary_alignment=True, match_source=AlignmentMatchSource.PRIMARY,
        )
    )
    db_session.flush()

    stats = se.compute_legacy_alignment_stats(db_session, pair)

    assert stats is not None
    assert stats.total == 1
    assert stats.status_counts == {"UNCHANGED": 1}
    assert stats.needs_review_fraction == 1.0


def test_compute_legacy_alignment_stats_none_when_no_run(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2020, "earlier")
    later_report = _report(db_session, company, 2021, "later")
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier_report.id, later_report_id=later_report.id, gap_months=12)
    db_session.add(pair)
    db_session.flush()

    assert se.compute_legacy_alignment_stats(db_session, pair) is None


# --- new-pipeline unit stats (DB-backed): provenance + unresolved handling ------


def test_compute_new_unit_stats_provenance_complete_with_no_source_blocks_flagged(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2020)
    extraction = _extraction_run(db_session, report)
    loc_run = _localization_run(db_session, report, extraction)
    instance = _schedule_instance(db_session, loc_run, report)
    unit_run = _unit_run(db_session, report, loc_run)
    _unit(db_session, unit_run, report, instance, word_count=64)

    stats = se.compute_new_unit_stats(db_session, report, SCHEDULE)

    assert stats.unit_run_status == "COMPLETED"
    assert stats.resolved_unit_count == 1
    # No SemanticUnitSourceBlock rows were created for this RESOLVED unit --
    # provenance must be flagged incomplete, never silently reported as OK.
    assert stats.provenance_complete is False


def test_compute_new_unit_stats_unresolved_upstream_review_reason_surfaced(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2017)
    extraction = _extraction_run(db_session, report)
    loc_run = _localization_run(db_session, report, extraction)
    unit_run = _unit_run(db_session, report, loc_run, review_reason="gross_margin: start heading not found -- no row created")

    stats = se.compute_new_unit_stats(db_session, report, SCHEDULE)

    assert stats.unit_run_status == "COMPLETED_WITH_WARNINGS"
    assert stats.resolved_unit_count == 0
    assert stats.review_reason == "gross_margin: start heading not found -- no row created"
    # No units at all (resolved or otherwise) means there's nothing to be
    # incomplete about -- vacuously "complete", never a false failure flag.
    assert stats.provenance_complete is True


def test_compute_new_unit_stats_no_run_at_all(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2016)
    stats = se.compute_new_unit_stats(db_session, report, SCHEDULE)
    assert stats.unit_run_status is None
    assert stats.resolved_unit_count == 0


# --- new-pipeline alignment stats: UNRESOLVED_UPSTREAM handling -----------------


def test_compute_new_alignment_stats_counts_unresolved_upstream(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2019, "earlier")
    later_report = _report(db_session, company, 2020, "later")
    earlier_extraction = _extraction_run(db_session, earlier_report)
    later_extraction = _extraction_run(db_session, later_report)
    earlier_loc = _localization_run(db_session, earlier_report, earlier_extraction)
    later_loc = _localization_run(db_session, later_report, later_extraction)
    earlier_instance = _schedule_instance(db_session, earlier_loc, earlier_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_loc)
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_report, earlier_instance)
    later_unit_run = _unit_run(
        db_session, later_report, later_loc, review_reason="gross_margin: start heading not found -- no row created"
    )

    pair = ReportPair(company_id=company.id, earlier_report_id=earlier_report.id, later_report_id=later_report.id, gap_months=12)
    db_session.add(pair)
    db_session.flush()

    arun = SemanticUnitAlignmentRun(
        report_pair_id=pair.id, earlier_semantic_unit_run_id=earlier_unit_run.id, later_semantic_unit_run_id=later_unit_run.id,
        schedule=SCHEDULE, algorithm_version="1", configuration_hash="x",
        status=SemanticUnitAlignmentRunStatus.COMPLETED_WITH_WARNINGS, completed_at=datetime.now(UTC),
    )
    db_session.add(arun)
    db_session.flush()
    db_session.add(
        SemanticUnitAlignment(
            alignment_run_id=arun.id, report_pair_id=pair.id, earlier_semantic_unit_id=earlier_unit.id,
            later_semantic_unit_id=None, status=SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM,
            confidence=AlignmentConfidence.NEEDS_REVIEW,
            evidence="later run completed with warnings and has no 'gross_margin' unit",
        )
    )
    db_session.flush()

    stats = se.compute_new_alignment_stats(db_session, pair, SCHEDULE)

    assert stats is not None
    assert stats.status_counts == {"UNRESOLVED_UPSTREAM": 1}
    # No AnalyticalDecisionRun exists for this pair -- must be reported as
    # such, never fabricated as an empty-but-successful run.
    assert stats.decision_run_status is None


def test_compute_new_alignment_stats_none_when_no_run(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2019, "earlier")
    later_report = _report(db_session, company, 2020, "later")
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier_report.id, later_report_id=later_report.id, gap_months=12)
    db_session.add(pair)
    db_session.flush()

    assert se.compute_new_alignment_stats(db_session, pair, SCHEDULE) is None


# --- run_shadow_evaluation: determinism and no mutation --------------------------


def test_run_shadow_evaluation_is_read_only_and_deterministic(db_session):
    company = _company(db_session, ticker="BEL")
    report = _report(db_session, company, 2020)
    extraction = _extraction_run(db_session, report)
    narrative = _narrative(db_session, extraction, report)
    seg = _seg_run(db_session, narrative, extraction)
    _passage(db_session, seg, report, 0, "some legacy passage text here")

    before_passage_count = db_session.scalar(select(Passage).where(Passage.report_id == report.id).limit(1)) is not None
    assert before_passage_count

    result_1 = se.run_shadow_evaluation(db_session, ["BEL"])
    result_2 = se.run_shadow_evaluation(db_session, ["BEL"])

    assert len(result_1.tickers) == 1
    assert result_1.tickers[0].legacy_passages == result_2.tickers[0].legacy_passages

    # No rows were added, removed, or mutated by running the evaluation twice.
    passages_after = db_session.scalars(select(Passage).where(Passage.report_id == report.id)).all()
    assert len(passages_after) == 1
    assert passages_after[0].raw_text == "some legacy passage text here"


def test_run_shadow_evaluation_unknown_ticker_produces_empty_evaluation(db_session):
    result = se.run_shadow_evaluation(db_session, ["NOPE"])
    assert len(result.tickers) == 1
    assert result.tickers[0].legacy_passages == []
    assert result.tickers[0].new_units == []


def test_render_markdown_report_includes_ticker_sections(db_session):
    company = _company(db_session, ticker="BEL")
    report = _report(db_session, company, 2020)
    extraction = _extraction_run(db_session, report)
    narrative = _narrative(db_session, extraction, report)
    seg = _seg_run(db_session, narrative, extraction)
    _passage(db_session, seg, report, 0, "some legacy passage text here")

    result = se.run_shadow_evaluation(db_session, ["BEL"])
    markdown = se.render_markdown_report(result)

    assert "## BEL" in markdown
    assert "Legacy passages" in markdown
