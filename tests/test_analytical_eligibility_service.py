"""DB-backed orchestration tests for `services.analytical_eligibility`
(Track 7C.3).

Builds the full persisted chain -- ExtractionRun -> ScheduleLocalizationRun
-> ScheduleInstance -> SemanticUnitRun -> SemanticUnit ->
SemanticUnitAlignmentRun -> SemanticUnitAlignment -- directly, since 7C.3
reads only that persisted output and must never re-run alignment or any
earlier stage.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from market_documents.models.company import Company
from market_documents.models.analytical_comparison import AnalyticalDecision, LexicalUnitComparison
from market_documents.models.enums import (
    AlignmentConfidence,
    AnalyticalDecisionRunStatus,
    AnalyticalMode,
    BoundaryConfidence,
    ExtractionStatus,
    MetadataStatus,
    NormalizedSchedule,
    ScheduleLocalizationRunStatus,
    ScheduleLocalizationStatus,
    SemanticUnitAlignmentRunStatus,
    SemanticUnitAlignmentStatus,
    SemanticUnitBoundaryStatus,
    SemanticUnitBoundaryStrategy,
    SemanticUnitRunStatus,
    SemanticUnitType,
)
from market_documents.models.extraction import ExtractionRun
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.schedule import ScheduleInstance, ScheduleLocalizationRun
from market_documents.models.semantic_unit import SemanticUnit, SemanticUnitRun
from market_documents.models.semantic_unit_alignment import SemanticUnitAlignment, SemanticUnitAlignmentRun
from market_documents.services import analytical_eligibility as ae

SCHEDULE = NormalizedSchedule.FINANCIAL_PERFORMANCE


def _company(session, ticker="BEL") -> Company:
    company = Company(ticker=ticker, company_name="Test Co")
    session.add(company)
    session.flush()
    return company


def _report(session, company, directory_year, **overrides) -> Report:
    defaults = dict(
        company_id=company.id,
        local_path=f"/tmp/{company.ticker}-{directory_year}.pdf",
        filename=f"{company.ticker}-{directory_year}.pdf",
        sha256=overrides.pop("sha256", f"{directory_year:064d}"),
        directory_year=directory_year,
        page_count=10,
        metadata_status=MetadataStatus.VALIDATED,
    )
    defaults.update(overrides)
    report = Report(**defaults)
    session.add(report)
    session.flush()
    return report


def _report_pair(session, company, earlier, later) -> ReportPair:
    pair = ReportPair(
        company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id,
        gap_months=12, is_transition=False,
    )
    session.add(pair)
    session.flush()
    return pair


def _extraction_run(session, report) -> ExtractionRun:
    run = ExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="x",
        status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _localization_run(session, report, extraction_run) -> ScheduleLocalizationRun:
    run = ScheduleLocalizationRun(
        report_id=report.id, extraction_run_id=extraction_run.id, schedule=SCHEDULE,
        algorithm_version="1", configuration_hash="x",
        status=ScheduleLocalizationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _schedule_instance(session, localization_run, report) -> ScheduleInstance:
    instance = ScheduleInstance(
        schedule_localization_run_id=localization_run.id, report_id=report.id, schedule=SCHEDULE,
        status=ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY, heading_text="Finance director's report",
        start_page=1, end_page=10, boundary_confidence=BoundaryConfidence.HIGH,
    )
    session.add(instance)
    session.flush()
    return instance


def _unit_run(session, report, localization_run, *, status=SemanticUnitRunStatus.COMPLETED, configuration_hash="units-v1") -> SemanticUnitRun:
    run = SemanticUnitRun(
        report_id=report.id, schedule_localization_run_id=localization_run.id, schedule=SCHEDULE,
        algorithm_version="1", configuration_hash=configuration_hash,
        status=status, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _unit(session, run, instance, report, unit_key, heading, source_text, *, resolved=True) -> SemanticUnit:
    unit = SemanticUnit(
        semantic_unit_run_id=run.id, report_id=report.id, schedule_instance_id=instance.id,
        unit_key=unit_key, unit_type=SemanticUnitType.HEADED_NARRATIVE_UNIT,
        source_heading=heading, start_page=2,
        boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
        boundary_status=SemanticUnitBoundaryStatus.RESOLVED if resolved else SemanticUnitBoundaryStatus.UNRESOLVED,
        boundary_confidence=BoundaryConfidence.HIGH if resolved else None,
        end_page=4 if resolved else None,
        source_text=source_text if resolved else None,
        word_count=len(source_text.split()) if resolved and source_text else None,
        extraction_note=None if resolved else "boundary could not be resolved",
    )
    session.add(unit)
    session.flush()
    return unit


def _alignment_run(session, pair, earlier_unit_run, later_unit_run, *, status=SemanticUnitAlignmentRunStatus.COMPLETED) -> SemanticUnitAlignmentRun:
    run = SemanticUnitAlignmentRun(
        report_pair_id=pair.id, earlier_semantic_unit_run_id=earlier_unit_run.id, later_semantic_unit_run_id=later_unit_run.id,
        schedule=SCHEDULE, algorithm_version="1", configuration_hash="align-v1",
        status=status, completed_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def _alignment(session, run, pair, *, earlier_unit=None, later_unit=None, status, confidence=AlignmentConfidence.HIGH, evidence="test") -> SemanticUnitAlignment:
    alignment = SemanticUnitAlignment(
        alignment_run_id=run.id, report_pair_id=pair.id,
        earlier_semantic_unit_id=earlier_unit.id if earlier_unit else None,
        later_semantic_unit_id=later_unit.id if later_unit else None,
        status=status, confidence=confidence, evidence=evidence,
    )
    session.add(alignment)
    session.flush()
    return alignment


EARLIER_TEXT = "The gross margin is dependent on the product and geographic mix of sales, compared with 18.5% in the prior year."
LATER_TEXT = "The gross margin is dependent on the product and geographic mix of sales, compared with 18.4% in the prior year. Market conditions shifted."


def _matched_bel_gross_margin(session, *, ticker="BEL"):
    company = _company(session, ticker)
    earlier_report = _report(session, company, 2018)
    later_report = _report(session, company, 2019)
    pair = _report_pair(session, company, earlier_report, later_report)

    earlier_extraction = _extraction_run(session, earlier_report)
    later_extraction = _extraction_run(session, later_report)
    earlier_localization = _localization_run(session, earlier_report, earlier_extraction)
    later_localization = _localization_run(session, later_report, later_extraction)
    earlier_instance = _schedule_instance(session, earlier_localization, earlier_report)
    later_instance = _schedule_instance(session, later_localization, later_report)

    earlier_unit_run = _unit_run(session, earlier_report, earlier_localization)
    later_unit_run = _unit_run(session, later_report, later_localization)
    earlier_unit = _unit(session, earlier_unit_run, earlier_instance, earlier_report, "gross_margin", "Gross Margin", EARLIER_TEXT)
    later_unit = _unit(session, later_unit_run, later_instance, later_report, "gross_margin", "Gross Margin", LATER_TEXT)

    alignment_run = _alignment_run(session, pair, earlier_unit_run, later_unit_run)
    alignment = _alignment(
        session, alignment_run, pair, earlier_unit=earlier_unit, later_unit=later_unit,
        status=SemanticUnitAlignmentStatus.MATCHED,
    )
    return pair, alignment_run, alignment


def test_integration_matched_alignment_produces_lexical_only_decision_and_metrics(db_session):
    pair, alignment_run, alignment = _matched_bel_gross_margin(db_session)

    outcome = ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    assert outcome.ineligible is False
    assert outcome.skipped is False
    run = outcome.run
    assert run.status == AnalyticalDecisionRunStatus.COMPLETED
    assert run.alignment_run_id == alignment_run.id

    decisions = db_session.scalars(select(AnalyticalDecision).where(AnalyticalDecision.decision_run_id == run.id)).all()
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.analytical_mode == AnalyticalMode.LEXICAL_ONLY
    assert decision.semantic_unit_alignment_id == alignment.id

    comparison = db_session.scalar(
        select(LexicalUnitComparison).where(LexicalUnitComparison.analytical_decision_id == decision.id)
    )
    assert comparison is not None
    assert comparison.semantic_unit_alignment_id == alignment.id
    assert comparison.earlier_word_count > 0
    assert comparison.later_word_count > 0
    assert comparison.tfidf_cosine is not None


def test_ineligible_when_no_current_alignment_run(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2018)
    later_report = _report(db_session, company, 2019)
    pair = _report_pair(db_session, company, earlier_report, later_report)

    outcome = ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    assert outcome.ineligible is True
    assert outcome.run is None
    assert db_session.scalars(select(AnalyticalDecision)).all() == []


def test_unresolved_upstream_alignment_produces_no_decision_or_metrics(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2019)
    later_report = _report(db_session, company, 2020)
    pair = _report_pair(db_session, company, earlier_report, later_report)
    earlier_extraction = _extraction_run(db_session, earlier_report)
    earlier_localization = _localization_run(db_session, earlier_report, earlier_extraction)
    earlier_instance = _schedule_instance(db_session, earlier_localization, earlier_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_localization)
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_instance, earlier_report, "gross_margin", "Gross Margin", EARLIER_TEXT)

    later_extraction = _extraction_run(db_session, later_report)
    later_localization = _localization_run(db_session, later_report, later_extraction)
    later_unit_run = _unit_run(db_session, later_report, later_localization, status=SemanticUnitRunStatus.COMPLETED_WITH_WARNINGS)

    alignment_run = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run, status=SemanticUnitAlignmentRunStatus.COMPLETED_WITH_WARNINGS)
    _alignment(
        db_session, alignment_run, pair, earlier_unit=earlier_unit, later_unit=None,
        status=SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, confidence=AlignmentConfidence.NEEDS_REVIEW,
    )

    outcome = ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    assert outcome.run.status == AnalyticalDecisionRunStatus.COMPLETED
    assert db_session.scalars(select(AnalyticalDecision)).all() == []
    assert db_session.scalars(select(LexicalUnitComparison)).all() == []


def test_added_and_removed_do_not_produce_lexical_metrics(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2018)
    later_report = _report(db_session, company, 2019)
    pair = _report_pair(db_session, company, earlier_report, later_report)
    earlier_extraction = _extraction_run(db_session, earlier_report)
    later_extraction = _extraction_run(db_session, later_report)
    earlier_localization = _localization_run(db_session, earlier_report, earlier_extraction)
    later_localization = _localization_run(db_session, later_report, later_extraction)
    earlier_instance = _schedule_instance(db_session, earlier_localization, earlier_report)
    later_instance = _schedule_instance(db_session, later_localization, later_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_localization)
    later_unit_run = _unit_run(db_session, later_report, later_localization)
    later_unit = _unit(db_session, later_unit_run, later_instance, later_report, "gross_margin", "Gross Margin", LATER_TEXT)

    alignment_run = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    _alignment(
        db_session, alignment_run, pair, earlier_unit=None, later_unit=later_unit,
        status=SemanticUnitAlignmentStatus.ADDED,
    )

    outcome = ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    decisions = db_session.scalars(select(AnalyticalDecision).where(AnalyticalDecision.decision_run_id == outcome.run.id)).all()
    assert len(decisions) == 1
    assert decisions[0].analytical_mode == AnalyticalMode.PRESENCE_STATUS_ONLY
    assert db_session.scalars(select(LexicalUnitComparison)).all() == []


def test_ambiguous_produces_no_decision(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2018)
    later_report = _report(db_session, company, 2019)
    pair = _report_pair(db_session, company, earlier_report, later_report)
    earlier_extraction = _extraction_run(db_session, earlier_report)
    later_extraction = _extraction_run(db_session, later_report)
    earlier_localization = _localization_run(db_session, earlier_report, earlier_extraction)
    later_localization = _localization_run(db_session, later_report, later_extraction)
    earlier_instance = _schedule_instance(db_session, earlier_localization, earlier_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_localization)
    later_unit_run = _unit_run(db_session, later_report, later_localization)
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_instance, earlier_report, "gross_margin", "Gross Margin", EARLIER_TEXT)

    alignment_run = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    _alignment(
        db_session, alignment_run, pair, earlier_unit=earlier_unit, later_unit=None,
        status=SemanticUnitAlignmentStatus.AMBIGUOUS, confidence=AlignmentConfidence.NEEDS_REVIEW,
    )

    outcome = ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    assert db_session.scalars(select(AnalyticalDecision)).all() == []


def test_unconfigured_unit_routes_not_eligible_and_run_completed_with_warnings(db_session):
    pair, alignment_run, alignment = _matched_bel_gross_margin(db_session, ticker="ZZZ")

    outcome = ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    assert outcome.run.status == AnalyticalDecisionRunStatus.COMPLETED_WITH_WARNINGS
    decisions = db_session.scalars(select(AnalyticalDecision).where(AnalyticalDecision.decision_run_id == outcome.run.id)).all()
    assert len(decisions) == 1
    assert decisions[0].analytical_mode == AnalyticalMode.NOT_ELIGIBLE
    assert decisions[0].review_reason is not None
    assert db_session.scalars(select(LexicalUnitComparison)).all() == []


def test_rerun_without_force_is_idempotent(db_session):
    pair, _, _ = _matched_bel_gross_margin(db_session)

    first = ae.run_analytical_comparison(db_session, pair, SCHEDULE)
    second = ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    assert second.skipped is True
    assert second.run.id == first.run.id
    assert len(db_session.scalars(select(AnalyticalDecision)).all()) == 1
    assert len(db_session.scalars(select(LexicalUnitComparison)).all()) == 1


def test_force_creates_new_run_without_duplicating_within_new_run(db_session):
    pair, _, _ = _matched_bel_gross_margin(db_session)

    first = ae.run_analytical_comparison(db_session, pair, SCHEDULE)
    second = ae.run_analytical_comparison(db_session, pair, SCHEDULE, force=True)

    assert second.skipped is False
    assert second.run.id != first.run.id
    assert len(db_session.scalars(select(AnalyticalDecision).where(AnalyticalDecision.decision_run_id == second.run.id)).all()) == 1


def test_get_current_decision_run_selects_latest_completed(db_session):
    pair, _, _ = _matched_bel_gross_margin(db_session)

    outcome = ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    current = ae.get_current_decision_run(db_session, pair.id, SCHEDULE)
    assert current is not None
    assert current.id == outcome.run.id


def test_no_dependency_on_passage_or_passage_alignment(db_session):
    """7C.3 must not read or write Passage/PassageAlignment or re-extract
    semantic units at all."""
    from market_documents.models.alignment import PassageAlignment
    from market_documents.models.passage import Passage

    pair, _, _ = _matched_bel_gross_margin(db_session)

    ae.run_analytical_comparison(db_session, pair, SCHEDULE)

    assert db_session.scalars(select(Passage)).all() == []
    assert db_session.scalars(select(PassageAlignment)).all() == []
