"""Integration tests exercising `PublicationBuilder` end to end against a
real (fixture-built) research pair and a real application test database.

Uses `_feature_fixtures.build_ready_pair` (the same helper Milestone 6's own
feature tests use) rather than a hand-rolled ORM setup, so this exercises
the actual `source_dataset.resolve_research_snapshot` pinned-lineage
resolution and `PublicationBuilder._build_rows` mapping against a real
FeatureRun/ReportPairFeatures/AlignmentRun/PassageAlignment population.
"""

import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _feature_fixtures import build_ready_pair  # noqa: E402
from test_cutover_comparison import (  # noqa: E402
    _alignment,
    _alignment_run,
    _decision,
    _decision_run,
    _lexical,
    _localization_run,
    _schedule_instance,
    _unit,
    _unit_run,
)

from market_documents.models.enums import SemanticUnitAlignmentStatus
from market_documents.publishing.models import (
    ApplicationState,
    Company as AppCompany,
    NarrativeUnitComparison,
    PassageComparison,
    PassageLanguageSignal,
    Publication,
    PublicationStatus,
    StructuredTableComparison,
)
from market_documents.publishing.publisher import PublicationBuilder, activate_publication, cleanup_publications
from market_documents.services.feature_extraction import build_features
from market_documents.services.financial_language_config import CORE_CATEGORIES


def _build_and_feature(db_session, ticker: str):
    pair, _alignment_outcome, _similarity_outcome = build_ready_pair(db_session, ticker=ticker)
    build_features(db_session, pair)
    db_session.flush()
    return pair


def test_build_produces_ready_publication(db_session, app_db_session):
    _build_and_feature(db_session, ticker="PUB1")

    builder = PublicationBuilder(publication_version="test-v1")
    publication = builder.build(db_session, app_db_session)

    assert publication.status in (PublicationStatus.READY.value, PublicationStatus.FAILED.value)
    # A FAILED status here would indicate a validation regression -- fail
    # loudly with the reason rather than silently accepting it.
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason
    assert publication.company_count == 1
    assert publication.report_count == 2
    assert publication.comparison_count == 1


def test_build_never_touches_application_state(db_session, app_db_session):
    _build_and_feature(db_session, ticker="PUB2")
    builder = PublicationBuilder(publication_version="test-v2")
    builder.build(db_session, app_db_session)

    state = app_db_session.get(ApplicationState, "active")
    assert state is None or state.active_publication_id is None


def test_rebuild_same_version_is_idempotent_on_ids(db_session, app_db_session):
    _build_and_feature(db_session, ticker="PUB3")
    builder = PublicationBuilder(publication_version="test-v3-idempotent")

    first = builder.build(db_session, app_db_session)
    app_db_session.flush()
    first_company_ids = {
        c.id for c in app_db_session.scalars(select(AppCompany).where(AppCompany.publication_id == first.id))
    }

    # Delete and rebuild under the identical version -- deterministic IDs
    # mean the same source data produces the same UUIDs.
    app_db_session.delete(app_db_session.get(Publication, first.id))
    app_db_session.flush()

    second = builder.build(db_session, app_db_session)
    second_company_ids = {
        c.id for c in app_db_session.scalars(select(AppCompany).where(AppCompany.publication_id == second.id))
    }
    assert first.id == second.id
    assert first_company_ids == second_company_ids


def test_activate_publication_requires_ready_status(db_session, app_db_session):
    _build_and_feature(db_session, ticker="PUB4")
    builder = PublicationBuilder(publication_version="test-v4")
    publication = builder.build(db_session, app_db_session)
    publication.status = PublicationStatus.FAILED.value
    app_db_session.flush()

    with pytest.raises(ValueError):
        activate_publication(app_db_session, publication.id)


def test_activate_supersedes_prior_active(db_session, app_db_session):
    _build_and_feature(db_session, ticker="PUB5A")
    _build_and_feature(db_session, ticker="PUB5B")

    builder_a = PublicationBuilder(publication_version="test-v5a")
    pub_a = builder_a.build(db_session, app_db_session)
    activate_publication(app_db_session, pub_a.id)

    builder_b = PublicationBuilder(publication_version="test-v5b")
    pub_b = builder_b.build(db_session, app_db_session)
    activate_publication(app_db_session, pub_b.id)

    app_db_session.refresh(pub_a)
    app_db_session.refresh(pub_b)
    assert pub_a.status == PublicationStatus.SUPERSEDED.value
    assert pub_b.status == PublicationStatus.ACTIVE.value

    state = app_db_session.get(ApplicationState, "active")
    assert state.active_publication_id == pub_b.id


def test_build_omits_zero_count_core_language_signals(db_session, app_db_session):
    _build_and_feature(db_session, ticker="PUB7")
    builder = PublicationBuilder(publication_version="test-v7")
    publication = builder.build(db_session, app_db_session)

    comparison_count = app_db_session.scalar(
        select(func.count()).select_from(PassageComparison).where(
            PassageComparison.publication_id == publication.id
        )
    )
    dense_count = comparison_count * 2 * len(CORE_CATEGORIES)

    core_signals = app_db_session.scalars(
        select(PassageLanguageSignal).where(
            PassageLanguageSignal.publication_id == publication.id,
            PassageLanguageSignal.subcategory.is_(None),
        )
    ).all()

    assert all(s.raw_count != 0 for s in core_signals)
    assert len(core_signals) < dense_count


def test_cleanup_never_deletes_active(db_session, app_db_session):
    _build_and_feature(db_session, ticker="PUB6")
    builder = PublicationBuilder(publication_version="test-v6")
    publication = builder.build(db_session, app_db_session)
    activate_publication(app_db_session, publication.id)

    removed = cleanup_publications(app_db_session, keep=0, dry_run=False)
    assert publication.id not in {p.id for p in removed}
    assert app_db_session.get(Publication, publication.id) is not None


def test_cleanup_dry_run_does_not_delete(db_session, app_db_session):
    _build_and_feature(db_session, ticker="PUB7")
    builder = PublicationBuilder(publication_version="test-v7")
    publication = builder.build(db_session, app_db_session)
    publication.status = PublicationStatus.FAILED.value
    app_db_session.flush()

    removed = cleanup_publications(app_db_session, keep=0, dry_run=True)
    assert publication.id in {p.id for p in removed}
    assert app_db_session.get(Publication, publication.id) is not None


def test_build_populates_cutover_comparison_rows_for_in_scope_pair(db_session, app_db_session):
    """Track 7A.3/7A.4: `PublicationBuilder.build()` must persist Track
    7C.6 narrative/structured comparison rows for an in-scope pair,
    regardless of the live `SEMANTIC_COMPARISON_CUTOVER_ENABLED` flag (the
    router used here is always force-enabled at publish time -- see
    `cutover_publishing.py`)."""
    pair = _build_and_feature(db_session, ticker="BEL")

    # Layer Track 7C.6 semantic-unit fixtures on top of the same pair so it
    # resolves for BEL's gross_margin scope entry.
    earlier_loc = _localization_run(db_session, pair.earlier_report)
    later_loc = _localization_run(db_session, pair.later_report)
    earlier_instance = _schedule_instance(db_session, earlier_loc, pair.earlier_report)
    later_instance = _schedule_instance(db_session, later_loc, pair.later_report)
    earlier_unit_run = _unit_run(db_session, pair.earlier_report, earlier_loc)
    later_unit_run = _unit_run(db_session, pair.later_report, later_loc)
    earlier_unit = _unit(db_session, earlier_unit_run, pair.earlier_report, earlier_instance, word_count=64)
    later_unit = _unit(db_session, later_unit_run, pair.later_report, later_instance, word_count=47)
    arun = _alignment_run(db_session, pair, earlier_unit_run, later_unit_run)
    alignment = _alignment(
        db_session, arun, pair, earlier_unit=earlier_unit, later_unit=later_unit,
        status=SemanticUnitAlignmentStatus.MATCHED,
    )
    drun = _decision_run(db_session, pair, arun)
    decision = _decision(db_session, drun, alignment)
    _lexical(db_session, decision, alignment)
    db_session.flush()

    builder = PublicationBuilder(publication_version="test-cutover-v1")
    publication = builder.build(db_session, app_db_session)

    assert publication.status == PublicationStatus.READY.value, publication.failure_reason
    assert publication.narrative_comparison_count == 1
    # BEL is not in NEW_PIPELINE_STRUCTURED_SCOPE.
    assert publication.structured_comparison_count == 0

    rows = app_db_session.scalars(select(NarrativeUnitComparison)).all()
    assert len(rows) == 1
    assert rows[0].unit_key == "gross_margin"
    assert rows[0].status == "RESOLVED"
    assert rows[0].comparison_backend == "SEMANTIC_UNIT"


def test_build_populates_both_narrative_and_structured_rows_for_act(db_session, app_db_session):
    """ACT is in scope for narrative units AND two structured table
    families at once -- these are not mutually exclusive. Since Track
    7D.2c, ACT has two in-scope FINANCIAL_PERFORMANCE narrative units
    (cfo_conclusion, healthcare_services_review)."""
    _build_and_feature(db_session, ticker="ACT")

    builder = PublicationBuilder(publication_version="test-cutover-v2")
    publication = builder.build(db_session, app_db_session)

    assert publication.status == PublicationStatus.READY.value, publication.failure_reason
    # No upstream Track 7C.1-7C.5 data was built for this pair, so every
    # in-scope row is published unresolved -- never silently omitted.
    assert publication.narrative_comparison_count == 2
    assert publication.structured_comparison_count == 2

    narrative_rows = app_db_session.scalars(select(NarrativeUnitComparison)).all()
    assert all(r.status == "UNRESOLVED_UPSTREAM" for r in narrative_rows)

    structured_rows = app_db_session.scalars(select(StructuredTableComparison)).all()
    assert {r.table_family_key for r in structured_rows} == {
        "ned_remuneration_policy_table",
        "total_remuneration_outcomes",
    }
    assert all(r.status == "UNRESOLVED_UPSTREAM" for r in structured_rows)
