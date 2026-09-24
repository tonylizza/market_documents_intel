"""Track 7F.9: publication of the unified topic-change metric fields, the
updated metric catalog, disabled-type validation, and the shared-artifact
behaviour of a language-signal-run regeneration (reuse since 7F.10)."""

import sys
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_versioned_shared_artifacts import _artifact_counts, _build_and_feature  # noqa: E402

from market_documents.publishing.findings import DISABLED_CANDIDATE_KEYS
from market_documents.publishing.models import (
    ArtifactPassageComparison,
    ArtifactPassageLanguageSignal,
    ArtifactRetrievalContext,
    DiscoveryItem,
    MetricDefinition,
    PublicationStatus,
    ReportComparison,
)
from market_documents.publishing.publisher import PublicationBuilder
from market_documents.publishing.validation import validate_persisted
from market_documents.services.financial_language_signals import (
    build_language_signals,
    get_current_pair_language_features,
)

_PASSTHROUGH = (
    "feature_eligible_primary_words_earlier",
    "feature_eligible_primary_words_later",
    "financial_condition_hits_earlier",
    "financial_condition_hits_later",
    "financial_condition_topic_change",
    "governance_topic_change",
    "uncertainty_topic_change",
    "uncertainty_count_change_per_1000",
    "uncertainty_supporting_hits",
    "uncertainty_opposing_hits",
    "uncertainty_change_consistency_ratio",
    "uncertainty_largest_passage_share",
    "positive_rate_change",
    "negative_rate_change",
)


def test_topic_change_fields_published_verbatim(db_session, app_db_session, tmp_path):
    pair, _run, _signals = _build_and_feature(db_session, tmp_path, ticker="TC1")
    lf = get_current_pair_language_features(db_session, pair.id)

    publication = PublicationBuilder(publication_version="tc-v1", include_qa_chunks=False).build(db_session, app_db_session)
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason
    comp = app_db_session.scalar(
        select(ReportComparison).where(
            ReportComparison.publication_id == publication.id, ReportComparison.source_report_pair_id == pair.id
        )
    )
    for name in _PASSTHROUGH:
        assert getattr(comp, name) == getattr(lf, name), name
    assert comp.uncertainty_hits_earlier == lf.uncertainty_count_earlier
    assert comp.uncertainty_hits_later == lf.uncertainty_count_later


def test_catalog_and_validation_reflect_frozen_methodology(db_session, app_db_session, tmp_path):
    _build_and_feature(db_session, tmp_path, ticker="TC2")
    publication = PublicationBuilder(publication_version="tc-v2", include_qa_chunks=False).build(db_session, app_db_session)
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason

    defs = {
        m.metric_key: m
        for m in app_db_session.scalars(select(MetricDefinition).where(MetricDefinition.publication_id == publication.id))
    }
    for key in ("financial_condition_topic_change", "governance_topic_change", "uncertainty_topic_change"):
        assert defs[key].unit == "rate_per_1000_words"
    for key in ("disclosure_change_score", "risk_language_introduction", "risk_language_removal", "new_rate_words"):
        assert "methodology under review" in defs[key].short_description
    for key in ("financial_condition_share_change", "governance_share_change"):
        assert "Supporting detail only" in defs[key].short_description

    disabled_items = app_db_session.scalar(
        select(func.count())
        .select_from(DiscoveryItem)
        .where(DiscoveryItem.publication_id == publication.id, DiscoveryItem.discovery_type.in_(DISABLED_CANDIDATE_KEYS))
    )
    assert disabled_items == 0
    summary = validate_persisted(app_db_session, publication.id)
    assert summary.passed, summary.failures


def test_signal_run_regeneration_reuses_signal_artifact_generation(db_session, app_db_session, tmp_path):
    """7F.9 measured a duplicate signal-artifact generation here, because the
    identity included the research `PassageLanguageSignal.id`. Since Track
    7F.10 (signals_v2, stable alignment-row identity) a fresh LanguageSignalRun
    with byte-identical per-passage content reuses every family, signals
    included (more cases: test_signal_artifact_identity.py)."""
    pair, _run, _signals = _build_and_feature(db_session, tmp_path, ticker="TC3")
    first = PublicationBuilder(publication_version="tc-v3a", include_qa_chunks=False).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason
    before = _artifact_counts(app_db_session)

    build_language_signals(db_session, pair, force=True)
    db_session.flush()
    second = PublicationBuilder(publication_version="tc-v3b", include_qa_chunks=False).build(db_session, app_db_session)
    assert second.status == PublicationStatus.READY.value, second.failure_reason
    after = _artifact_counts(app_db_session)

    assert after[ArtifactPassageComparison.__tablename__] == before[ArtifactPassageComparison.__tablename__]
    assert after[ArtifactRetrievalContext.__tablename__] == before[ArtifactRetrievalContext.__tablename__]
    signals = ArtifactPassageLanguageSignal.__tablename__
    assert after[signals] == before[signals] > 0
