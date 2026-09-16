"""Tests for Track 7C.6's `services.cutover_preflight.run_cutover_preflight`
-- read-only READY/MISSING_DATA/UNRESOLVED verdicts per configured scope
entry. Reuses no mutation of any kind; verifies only reporting logic.
"""

from market_documents.models.company import Company
from market_documents.services.cutover_preflight import (
    MISSING_DATA,
    READY,
    UNRESOLVED,
    run_cutover_preflight,
)
from tests.test_cutover_comparison import (
    _alignment,
    _alignment_run,
    _company,
    _decision,
    _decision_run,
    _lexical,
    _localization_run,
    _pair,
    _report,
    _schedule_instance,
    _unit,
    _unit_run,
)
from market_documents.models.enums import SemanticUnitAlignmentStatus


def test_preflight_missing_data_when_no_reports_exist(db_session):
    results = run_cutover_preflight(db_session)
    labels = {r.scope_label: r for r in results}
    assert labels["BEL FINANCIAL_PERFORMANCE gross_margin"].verdict == MISSING_DATA
    assert labels["ACT FINANCIAL_PERFORMANCE cfo_conclusion"].verdict == MISSING_DATA
    assert labels["ACT ned_remuneration_policy_table"].verdict == MISSING_DATA
    assert labels["ACT total_remuneration_outcomes"].verdict == MISSING_DATA


def test_preflight_unresolved_when_alignment_exists_but_never_resolves(db_session):
    company = _company(db_session, "BEL")
    earlier_report = _report(db_session, company, 2019, "e")
    later_report = _report(db_session, company, 2020, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    earlier_loc = _localization_run(db_session, earlier_report)
    later_loc = _localization_run(db_session, later_report)
    earlier_instance = _schedule_instance(db_session, earlier_loc, earlier_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_loc)
    later_unit_run = _unit_run(db_session, later_report, later_loc, clean=False)
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_report, earlier_instance)

    arun = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    _alignment(
        db_session, arun, pair, earlier_unit=earlier_unit, later_unit=None,
        status=SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM,
    )

    results = run_cutover_preflight(db_session)
    labels = {r.scope_label: r for r in results}
    assert labels["BEL FINANCIAL_PERFORMANCE gross_margin"].verdict == UNRESOLVED


def test_preflight_ready_when_a_pair_resolves(db_session):
    company = _company(db_session, "BEL")
    earlier_report = _report(db_session, company, 2018, "e")
    later_report = _report(db_session, company, 2019, "l")
    pair = _pair(db_session, company, earlier_report, later_report)

    earlier_loc = _localization_run(db_session, earlier_report)
    later_loc = _localization_run(db_session, later_report)
    earlier_instance = _schedule_instance(db_session, earlier_loc, earlier_report)
    later_instance = _schedule_instance(db_session, later_loc, later_report)
    earlier_unit_run = _unit_run(db_session, earlier_report, earlier_loc)
    later_unit_run = _unit_run(db_session, later_report, later_loc)
    earlier_unit = _unit(db_session, earlier_unit_run, earlier_report, earlier_instance, word_count=64)
    later_unit = _unit(db_session, later_unit_run, later_report, later_instance, word_count=47)

    arun = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    alignment = _alignment(
        db_session, arun, pair, earlier_unit=earlier_unit, later_unit=later_unit,
        status=SemanticUnitAlignmentStatus.MATCHED,
    )
    drun = _decision_run(db_session, pair, arun)
    decision = _decision(db_session, drun, alignment)
    _lexical(db_session, decision, alignment)

    results = run_cutover_preflight(db_session)
    labels = {r.scope_label: r for r in results}
    assert labels["BEL FINANCIAL_PERFORMANCE gross_margin"].verdict == READY
