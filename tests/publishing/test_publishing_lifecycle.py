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

from market_documents.publishing.models import (
    ApplicationState,
    Company as AppCompany,
    PassageComparison,
    PassageLanguageSignal,
    Publication,
    PublicationStatus,
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
