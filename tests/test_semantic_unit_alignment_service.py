"""DB-backed orchestration tests for `services.semantic_unit_alignment`
(Track 7C.2).

Builds the full persisted chain -- ExtractionRun -> ScheduleLocalizationRun
-> ScheduleInstance -> SemanticUnitRun -> SemanticUnit -- directly (no
canonical/schedule/extraction services are invoked), since 7C.2 reads only
this persisted output and must never re-run any earlier stage.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from market_documents.models.company import Company
from market_documents.models.enums import (
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
from market_documents.models.semantic_unit_alignment import SemanticUnitAlignment
from market_documents.services import semantic_unit_alignment as sua

SCHEDULE = NormalizedSchedule.FINANCIAL_PERFORMANCE


def _company(session, ticker="TST") -> Company:
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


def _unit_run(session, report, localization_run, *, status=SemanticUnitRunStatus.COMPLETED, review_reason=None, configuration_hash="units-v1") -> SemanticUnitRun:
    run = SemanticUnitRun(
        report_id=report.id, schedule_localization_run_id=localization_run.id, schedule=SCHEDULE,
        algorithm_version="1", configuration_hash=configuration_hash,
        status=status, completed_at=datetime.now(UTC), review_reason=review_reason,
    )
    session.add(run)
    session.flush()
    return run


def _unit(session, run, instance, report, unit_key, heading, *, resolved=True) -> SemanticUnit:
    unit = SemanticUnit(
        semantic_unit_run_id=run.id, report_id=report.id, schedule_instance_id=instance.id,
        unit_key=unit_key, unit_type=SemanticUnitType.HEADED_NARRATIVE_UNIT,
        source_heading=heading, start_page=2,
        boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
        boundary_status=SemanticUnitBoundaryStatus.RESOLVED if resolved else SemanticUnitBoundaryStatus.UNRESOLVED,
        boundary_confidence=BoundaryConfidence.HIGH if resolved else None,
        end_page=4 if resolved else None,
        source_text="some narrative text" if resolved else None,
        word_count=3 if resolved else None,
        extraction_note=None if resolved else "boundary could not be resolved",
    )
    session.add(unit)
    session.flush()
    return unit


def _full_pair_with_units(session, *, earlier_units, later_units, earlier_clean=True, later_clean=True):
    """earlier_units/later_units: list of (unit_key, heading, resolved) tuples."""
    company = _company(session)
    earlier_report = _report(session, company, 2019)
    later_report = _report(session, company, 2020)
    pair = _report_pair(session, company, earlier_report, later_report)

    earlier_extraction = _extraction_run(session, earlier_report)
    later_extraction = _extraction_run(session, later_report)
    earlier_localization = _localization_run(session, earlier_report, earlier_extraction)
    later_localization = _localization_run(session, later_report, later_extraction)
    earlier_instance = _schedule_instance(session, earlier_localization, earlier_report)
    later_instance = _schedule_instance(session, later_localization, later_report)

    earlier_status = SemanticUnitRunStatus.COMPLETED if earlier_clean else SemanticUnitRunStatus.COMPLETED_WITH_WARNINGS
    later_status = SemanticUnitRunStatus.COMPLETED if later_clean else SemanticUnitRunStatus.COMPLETED_WITH_WARNINGS
    earlier_run = _unit_run(session, earlier_report, earlier_localization, status=earlier_status, review_reason=None if earlier_clean else "warned")
    later_run = _unit_run(session, later_report, later_localization, status=later_status, review_reason=None if later_clean else "warned")

    for unit_key, heading, resolved in earlier_units:
        _unit(session, earlier_run, earlier_instance, earlier_report, unit_key, heading, resolved=resolved)
    for unit_key, heading, resolved in later_units:
        _unit(session, later_run, later_instance, later_report, unit_key, heading, resolved=resolved)

    return pair, earlier_run, later_run


def test_integration_exact_match_produces_matched_alignment(db_session):
    pair, earlier_run, later_run = _full_pair_with_units(
        db_session,
        earlier_units=[("gross_margin", "Gross Margin", True)],
        later_units=[("gross_margin", "Gross Margin", True)],
    )

    outcome = sua.run_alignment(db_session, pair, SCHEDULE)

    assert outcome.skipped is False
    assert outcome.ineligible is False
    run = outcome.run
    assert run.status == SemanticUnitAlignmentRunStatus.COMPLETED
    assert run.earlier_semantic_unit_run_id == earlier_run.id
    assert run.later_semantic_unit_run_id == later_run.id

    alignments = db_session.scalars(select(SemanticUnitAlignment).where(SemanticUnitAlignment.alignment_run_id == run.id)).all()
    assert len(alignments) == 1
    assert alignments[0].status == SemanticUnitAlignmentStatus.MATCHED


def test_ineligible_when_one_side_has_no_current_successful_unit_run(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2019)
    later_report = _report(db_session, company, 2020)
    pair = _report_pair(db_session, company, earlier_report, later_report)
    # Earlier side never had schedule localization/extraction run at all.

    outcome = sua.run_alignment(db_session, pair, SCHEDULE)

    assert outcome.ineligible is True
    assert "earlier" in outcome.ineligible_reason
    assert outcome.run is None
    assert db_session.scalars(select(SemanticUnitAlignment)).all() == []


def test_rerun_without_force_is_idempotent(db_session):
    pair, _, _ = _full_pair_with_units(
        db_session,
        earlier_units=[("gross_margin", "Gross Margin", True)],
        later_units=[("gross_margin", "Gross Margin", True)],
    )

    first = sua.run_alignment(db_session, pair, SCHEDULE)
    second = sua.run_alignment(db_session, pair, SCHEDULE)

    assert second.skipped is True
    assert second.run.id == first.run.id


def test_force_creates_new_run(db_session):
    pair, _, _ = _full_pair_with_units(
        db_session,
        earlier_units=[("gross_margin", "Gross Margin", True)],
        later_units=[("gross_margin", "Gross Margin", True)],
    )

    first = sua.run_alignment(db_session, pair, SCHEDULE)
    second = sua.run_alignment(db_session, pair, SCHEDULE, force=True)

    assert second.skipped is False
    assert second.run.id != first.run.id


def test_get_current_alignment_run_selects_latest_completed(db_session):
    pair, _, _ = _full_pair_with_units(
        db_session,
        earlier_units=[("gross_margin", "Gross Margin", True)],
        later_units=[("gross_margin", "Gross Margin", True)],
    )

    outcome = sua.run_alignment(db_session, pair, SCHEDULE)

    current = sua.get_current_alignment_run(db_session, pair.id, SCHEDULE)
    assert current is not None
    assert current.id == outcome.run.id


def test_uses_current_successful_semantic_unit_run_not_a_failed_rerun(db_session):
    pair, earlier_run, later_run = _full_pair_with_units(
        db_session,
        earlier_units=[("gross_margin", "Gross Margin", True)],
        later_units=[("gross_margin", "Gross Margin", True)],
    )
    # A later, FAILED SemanticUnitRun for the same report/schedule must not
    # be selected over the existing successful one.
    stale_localization = _localization_run(db_session, later_run.report, db_session.get(ExtractionRun, later_run.schedule_localization_run.extraction_run_id))
    failed_run = SemanticUnitRun(
        report_id=later_run.report_id, schedule_localization_run_id=stale_localization.id, schedule=SCHEDULE,
        algorithm_version="1", configuration_hash="units-v2",
        status=SemanticUnitRunStatus.FAILED, completed_at=datetime.now(UTC), error_message="boom",
    )
    db_session.add(failed_run)
    db_session.flush()

    outcome = sua.run_alignment(db_session, pair, SCHEDULE)

    assert outcome.run.later_semantic_unit_run_id == later_run.id


def test_missing_upstream_unit_does_not_become_false_removed_event(db_session):
    """The BEL 2020 gross_margin case, reproduced end to end: earlier has a
    resolved unit, later's run completed WITH warnings and has no row at
    all for that unit_key."""
    pair, _, later_run = _full_pair_with_units(
        db_session,
        earlier_units=[("gross_margin", "Gross Margin", True)],
        later_units=[],
        earlier_clean=True,
        later_clean=False,
    )

    outcome = sua.run_alignment(db_session, pair, SCHEDULE)

    assert outcome.run.status == SemanticUnitAlignmentRunStatus.COMPLETED_WITH_WARNINGS
    alignments = db_session.scalars(select(SemanticUnitAlignment).where(SemanticUnitAlignment.alignment_run_id == outcome.run.id)).all()
    assert len(alignments) == 1
    assert alignments[0].status == SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM
    assert alignments[0].status != SemanticUnitAlignmentStatus.REMOVED


def test_no_dependency_on_passage_or_passage_alignment(db_session):
    """7C.2 must not read or write Passage/PassageAlignment at all."""
    from market_documents.models.alignment import PassageAlignment
    from market_documents.models.passage import Passage

    pair, _, _ = _full_pair_with_units(
        db_session,
        earlier_units=[("gross_margin", "Gross Margin", True)],
        later_units=[("gross_margin", "Gross Margin", True)],
    )

    sua.run_alignment(db_session, pair, SCHEDULE)

    assert db_session.scalars(select(Passage)).all() == []
    assert db_session.scalars(select(PassageAlignment)).all() == []
