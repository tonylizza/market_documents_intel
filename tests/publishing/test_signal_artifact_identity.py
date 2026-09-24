"""Track 7F.10: stable `app_artifacts.passage_language_signals` identity.

A metric-only research `SIGNAL_VERSION` rerun (fresh `LanguageSignalRun`,
new research `PassageLanguageSignal.id`s, identical per-passage content)
must reuse the existing signal-artifact generation 100%; a genuine
per-passage content change must fail loudly unless
`LANGUAGE_SIGNAL_ARTIFACT_VERSION` is bumped, in which case it gets its own
isolated generation; reference-counted GC keeps working on the new key.
"""

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_versioned_shared_artifacts import _artifact_counts, _build_and_feature  # noqa: E402

from market_documents.models.enums import ReportSide
from market_documents.models.financial_language import PassageLanguageSignal as ResearchSignal
from market_documents.publishing import labels
from market_documents.publishing.models import (
    ApplicationState,
    ArtifactPassageComparison,
    ArtifactPassageLanguageSignal,
    ArtifactRetrievalContext,
    PassageLanguageSignal,
    PublicationStatus,
)
from market_documents.publishing.publisher import (
    PublicationBuilder,
    _signal_artifact_id,
    activate_publication,
    cleanup_publications,
    gc_orphaned_artifact_rows,
)
from market_documents.publishing.validation import validate_persisted
from market_documents.services.financial_language_signals import (
    build_language_signals,
    get_current_language_signal_run,
)

_BUMPED = "signals_v3_test"


def _build(db_session, app_db_session, version: str):
    publication = PublicationBuilder(publication_version=version, include_qa_chunks=False).build(
        db_session, app_db_session
    )
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason
    return publication


def _thin_artifact_ids(app_db_session, publication_id) -> set[uuid.UUID]:
    return set(
        app_db_session.scalars(
            select(PassageLanguageSignal.language_signal_artifact_id).where(
                PassageLanguageSignal.publication_id == publication_id
            )
        )
    )


def _rerun_signals(db_session, pair) -> None:
    before = get_current_language_signal_run(db_session, pair.id)
    build_language_signals(db_session, pair, force=True)
    db_session.flush()
    after = get_current_language_signal_run(db_session, pair.id)
    assert after.id != before.id


def _change_current_signal_content(db_session, pair) -> None:
    """A genuine per-passage change (stand-in for a taxonomy/negation edit):
    +1 uncertainty hit on every signal row of the current run."""
    run = get_current_language_signal_run(db_session, pair.id)
    signals = list(db_session.scalars(select(ResearchSignal).where(ResearchSignal.language_signal_run_id == run.id)))
    assert signals
    for signal in signals:
        signal.uncertainty_count += 1
    db_session.flush()


def test_identity_is_stable_alignment_key_not_research_signal_id():
    alignment_id = uuid.uuid4()
    a = SimpleNamespace(id=uuid.uuid4(), passage_alignment_id=alignment_id, report_side=ReportSide.EARLIER)
    b = SimpleNamespace(id=uuid.uuid4(), passage_alignment_id=alignment_id, report_side=ReportSide.EARLIER)
    assert _signal_artifact_id(a, "uncertainty", None) == _signal_artifact_id(b, "uncertainty", None)

    later = SimpleNamespace(id=a.id, passage_alignment_id=alignment_id, report_side=ReportSide.LATER)
    realigned = SimpleNamespace(id=a.id, passage_alignment_id=uuid.uuid4(), report_side=ReportSide.EARLIER)
    base = _signal_artifact_id(a, "uncertainty", None)
    assert _signal_artifact_id(later, "uncertainty", None) != base
    assert _signal_artifact_id(realigned, "uncertainty", None) != base
    assert _signal_artifact_id(a, "negative", None) != base
    assert _signal_artifact_id(a, "governance", "board") != _signal_artifact_id(a, "governance", "audit")
    with patch("market_documents.publishing.publisher.labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION", _BUMPED):
        assert _signal_artifact_id(a, "uncertainty", None) != base


def test_identical_content_signal_rerun_reuses_signal_artifacts_fully(db_session, app_db_session, tmp_path):
    pair, _run, _outcome = _build_and_feature(db_session, tmp_path, ticker="SAI1")
    first = _build(db_session, app_db_session, "sai1-v1")
    before = _artifact_counts(app_db_session)
    first_ids = _thin_artifact_ids(app_db_session, first.id)
    assert first_ids

    _rerun_signals(db_session, pair)
    second = _build(db_session, app_db_session, "sai1-v2")

    assert _artifact_counts(app_db_session) == before
    second_ids = _thin_artifact_ids(app_db_session, second.id)
    assert second_ids == first_ids  # 100% reuse
    rows = list(app_db_session.scalars(select(ArtifactPassageLanguageSignal)))
    assert all(r.language_signal_artifact_version == labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION for r in rows)
    assert all(r.source_signal_id is None and r.source_passage_alignment_id is not None for r in rows)
    content_keys = [
        (r.source_passage_alignment_id, r.report_side, r.category, r.subcategory, r.content_hash) for r in rows
    ]
    assert len(content_keys) == len(set(content_keys))  # zero duplicate content rows
    assert validate_persisted(app_db_session, second.id).passed


def test_changed_signal_content_without_version_bump_fails_loudly(db_session, app_db_session, tmp_path):
    pair, _run, _outcome = _build_and_feature(db_session, tmp_path, ticker="SAI2")
    _build(db_session, app_db_session, "sai2-v1")

    _rerun_signals(db_session, pair)
    _change_current_signal_content(db_session, pair)
    with pytest.raises(RuntimeError, match="content hash mismatch"):
        PublicationBuilder(publication_version="sai2-v2", include_qa_chunks=False).build(db_session, app_db_session)


def test_changed_signal_content_with_version_bump_creates_isolated_generation(db_session, app_db_session, tmp_path):
    pair, _run, _outcome = _build_and_feature(db_session, tmp_path, ticker="SAI3")
    first = _build(db_session, app_db_session, "sai3-v1")
    activate_publication(app_db_session, first.id)
    old_rows = {r.id: r.content_hash for r in app_db_session.scalars(select(ArtifactPassageLanguageSignal))}

    _rerun_signals(db_session, pair)
    _change_current_signal_content(db_session, pair)
    with patch("market_documents.publishing.publisher.labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION", _BUMPED):
        second = _build(db_session, app_db_session, "sai3-v2")
    activate_publication(app_db_session, second.id)

    # Old generation untouched; new generation disjoint.
    for artifact_id, content_hash in old_rows.items():
        assert app_db_session.get(ArtifactPassageLanguageSignal, artifact_id).content_hash == content_hash
    second_ids = _thin_artifact_ids(app_db_session, second.id)
    assert second_ids.isdisjoint(old_rows)
    assert _thin_artifact_ids(app_db_session, first.id) == set(old_rows)

    def _active_uncertainty() -> tuple[set[str], int]:
        rows = app_db_session.execute(
            text(
                "SELECT s.language_signal_artifact_version, v.raw_count "
                "FROM app.current_passage_language_signals v "
                "JOIN app_artifacts.passage_language_signals s ON s.id = v.language_signal_artifact_id "
                "WHERE v.category = 'uncertainty'"
            )
        ).all()
        return {r[0] for r in rows}, sum(r[1] for r in rows)

    versions_new, total_new = _active_uncertainty()
    assert versions_new == {_BUMPED}

    # Rollback read path (same mechanism as test_versioned_shared_artifacts).
    app_db_session.get(ApplicationState, "active").active_publication_id = first.id
    app_db_session.flush()
    versions_old, total_old = _active_uncertainty()
    assert versions_old == {labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION}
    assert total_new == total_old + len(_thin_uncertainty_rows(app_db_session, first.id))


def _thin_uncertainty_rows(app_db_session, publication_id) -> list:
    return list(
        app_db_session.scalars(
            select(PassageLanguageSignal).where(
                PassageLanguageSignal.publication_id == publication_id, PassageLanguageSignal.category == "uncertainty"
            )
        )
    )


def test_gc_keeps_shared_signal_artifacts_until_last_reference_is_cleaned(db_session, app_db_session, tmp_path):
    pair, _run, _outcome = _build_and_feature(db_session, tmp_path, ticker="SAI4")
    p1 = _build(db_session, app_db_session, "sai4-v1")
    shared_ids = _thin_artifact_ids(app_db_session, p1.id)

    _rerun_signals(db_session, pair)
    p2 = _build(db_session, app_db_session, "sai4-v2")
    assert _thin_artifact_ids(app_db_session, p2.id) == shared_ids

    _rerun_signals(db_session, pair)
    _change_current_signal_content(db_session, pair)
    with patch("market_documents.publishing.publisher.labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION", _BUMPED):
        p3 = _build(db_session, app_db_session, "sai4-v3")
    activate_publication(app_db_session, p3.id)

    # Retain active (P3) + one rollback (P2): P1 goes, the shared generation stays.
    assert {p.id for p in cleanup_publications(app_db_session, keep=2)} == {p1.id}
    assert gc_orphaned_artifact_rows(app_db_session)["passage_language_signals"] == 0
    assert all(app_db_session.get(ArtifactPassageLanguageSignal, i) is not None for i in shared_ids)
    assert validate_persisted(app_db_session, p2.id).passed
    assert validate_persisted(app_db_session, p3.id).passed

    # Last reference gone -> the old generation (and only it) is collected.
    assert {p.id for p in cleanup_publications(app_db_session, keep=1)} == {p2.id}
    assert gc_orphaned_artifact_rows(app_db_session)["passage_language_signals"] == len(shared_ids)
    remaining = set(app_db_session.scalars(select(ArtifactPassageLanguageSignal.language_signal_artifact_version)))
    assert remaining == {_BUMPED}
    assert validate_persisted(app_db_session, p3.id).passed
    assert app_db_session.scalar(select(func.count()).select_from(ArtifactPassageComparison)) > 0
    assert app_db_session.scalar(select(func.count()).select_from(ArtifactRetrievalContext)) > 0
