"""Track 7F.7a.5: versioned shared artifact implementation & local
qualification.

Exercises the properties docs/versioned-shared-artifacts-implementation-
7f7a5.md's final verdict depends on: unchanged-republish reuse across all
four families (also the QA-chunk stability confirmation gate -- see
`test_unchanged_republish_reuses_all_four_families_including_qa_chunks`'s
docstring), per-family version-bump isolation, publication immutability,
rollback correctness, GC reference-safety, and the defensive content-hash
guard. Uses the same `_feature_fixtures.build_ready_pair` real end-to-end
fixture as `test_publishing_corpus_sharing.py`.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _language_fixtures import build_language_ready_pair, write_synthetic_lm_csv  # noqa: E402

from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, PassageType
from market_documents.publishing.models import (
    ArtifactPassageComparison,
    ArtifactPassageLanguageSignal,
    ArtifactQaChunk,
    ArtifactRetrievalContext,
)
from market_documents.publishing.models import PassageComparison as AppPassageComparison
from market_documents.publishing.models import PassageLanguageSignal as AppPassageLanguageSignal
from market_documents.publishing.models import Publication, PublicationStatus
from market_documents.publishing.models import QaChunk as AppQaChunk
from market_documents.publishing.models import RetrievalContext as AppRetrievalContext
from market_documents.publishing.publisher import (
    PublicationBuilder,
    activate_publication,
    cleanup_publications,
    gc_orphaned_artifact_rows,
)
from market_documents.services import financial_language_dictionary_import as di
from market_documents.services.financial_language_signals import build_language_signals

_ARTIFACT_MODELS = (
    ArtifactPassageComparison,
    ArtifactRetrievalContext,
    ArtifactPassageLanguageSignal,
    ArtifactQaChunk,
)

# A single UNCHANGED matched passage whose text carries several Loughran-
# McDonald-dictionary-shaped terms (see `_language_fixtures.LM_CSV_ROWS`)
# repeated enough to survive the alignment-length/similarity thresholds --
# guarantees `build_language_signals` produces nonzero-count core-category
# rows, unlike `_feature_fixtures.build_ready_pair`'s default filler text
# (all "disclosure{i}" tokens, none dictionary terms), which is why this
# module uses `_language_fixtures.build_language_ready_pair` instead of
# `_feature_fixtures.build_ready_pair`.
_SIGNAL_TEXT = " ".join(["loss strong uncertain must always could"] * 10)


def _build_and_feature(db_session, tmp_path, ticker: str):
    """Full pipeline this module's tests need: an UNCHANGED-matched pair
    with real Loughran-McDonald category hits, ready for `PublicationBuilder`
    to publish all four artifact families (`build_language_signals` must run
    BEFORE the publish, exactly like `test_financial_language_signals.py`)."""
    pair, alignment_run, _earlier, _later, _feature_outcome = build_language_ready_pair(
        db_session,
        ticker=ticker,
        earlier_texts=[(_SIGNAL_TEXT, PassageType.PARAGRAPH)],
        later_texts=[(_SIGNAL_TEXT, PassageType.PARAGRAPH)],
        rows=[
            {"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
        ],
    )
    lm_path = write_synthetic_lm_csv(tmp_path, f"{ticker}_lm.csv")
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")
    signal_outcome = build_language_signals(db_session, pair)
    db_session.flush()
    return pair, alignment_run, signal_outcome


def _artifact_counts(app_db_session) -> dict[str, int]:
    return {
        model.__tablename__: app_db_session.scalar(select(func.count()).select_from(model))
        for model in _ARTIFACT_MODELS
    }


def test_unchanged_republish_reuses_all_four_families_including_qa_chunks(db_session, app_db_session, tmp_path):
    """Sections 10/11 (unchanged + metric-only republish) AND section 9 (the
    QA-chunk stability confirmation gate) in one test: two publications,
    different `publication_version`, built with `include_qa_chunks=True`
    from the SAME unchanged source data, under the same artifact versions.
    Zero new `app_artifacts.*` rows may be created on the second build --
    if QA chunking or embedding were even slightly nondeterministic across
    the two builds, the SAME deterministic id would be computed for
    different content and `_check_content_hash` would raise loudly (the
    build would fail, not silently produce a wrong result), so a READY
    second build with unchanged artifact counts is itself the gate's
    passing result: 100% identity/content stability, zero exceptions."""
    _build_and_feature(db_session, tmp_path, ticker="VSA1")

    first = PublicationBuilder(publication_version="vsa-v1", include_qa_chunks=True).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason
    assert first.qa_chunk_count > 0, "fixture must exercise the QA-chunk family for this test to be meaningful"

    counts_after_first = _artifact_counts(app_db_session)
    assert all(c > 0 for c in counts_after_first.values())

    second = PublicationBuilder(publication_version="vsa-v2", include_qa_chunks=True).build(db_session, app_db_session)
    assert second.status == PublicationStatus.READY.value, second.failure_reason
    assert second.qa_chunk_count == first.qa_chunk_count

    counts_after_second = _artifact_counts(app_db_session)
    assert counts_after_second == counts_after_first, (
        "unchanged republish must add zero app_artifacts rows in any family"
    )

    # Thin per-publication layer still grows -- membership rows are
    # genuinely publication-specific, only the bulk artifact payload is
    # shared (mirrors test_publishing_corpus_sharing.py's isolation check).
    first_pc_ids = {
        r.id for r in app_db_session.scalars(select(AppPassageComparison).where(AppPassageComparison.publication_id == first.id))
    }
    second_pc_ids = {
        r.id for r in app_db_session.scalars(select(AppPassageComparison).where(AppPassageComparison.publication_id == second.id))
    }
    assert first_pc_ids.isdisjoint(second_pc_ids)
    assert len(first_pc_ids) == len(second_pc_ids) > 0

    # But every thin row from both publications resolves to the SAME shared
    # artifact generation -- this is the actual reuse property, not just an
    # unchanged row count.
    first_artifact_ids = {
        r.alignment_artifact_id
        for r in app_db_session.scalars(select(AppPassageComparison).where(AppPassageComparison.publication_id == first.id))
    }
    second_artifact_ids = {
        r.alignment_artifact_id
        for r in app_db_session.scalars(select(AppPassageComparison).where(AppPassageComparison.publication_id == second.id))
    }
    assert first_artifact_ids == second_artifact_ids
    assert None not in first_artifact_ids


def test_language_signal_version_bump_isolates_only_that_family(db_session, app_db_session, tmp_path):
    """Section 12.A: bumping `LANGUAGE_SIGNAL_ARTIFACT_VERSION` alone creates
    a new `passage_language_signals` generation, leaves the old generation
    intact, and leaves the other three families' generations reused."""
    _build_and_feature(db_session, tmp_path, ticker="VSA2")

    first = PublicationBuilder(publication_version="vsa2-v1", include_qa_chunks=True).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason
    counts_before = _artifact_counts(app_db_session)

    with patch("market_documents.publishing.publisher.labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION", "signals_v2_test"):
        second = PublicationBuilder(publication_version="vsa2-v2", include_qa_chunks=True).build(
            db_session, app_db_session
        )
    assert second.status == PublicationStatus.READY.value, second.failure_reason
    assert second.language_signal_artifact_version == "signals_v2_test"

    counts_after = _artifact_counts(app_db_session)
    assert counts_after["passage_language_signals"] > counts_before["passage_language_signals"]
    assert counts_after["passage_comparisons"] == counts_before["passage_comparisons"]
    assert counts_after["retrieval_contexts"] == counts_before["retrieval_contexts"]
    assert counts_after["qa_chunks"] == counts_before["qa_chunks"]

    # The old generation is still there, untouched, and P1 still resolves to it.
    old_signal_ids = {
        r.language_signal_artifact_id
        for r in app_db_session.scalars(select(AppPassageLanguageSignal).where(AppPassageLanguageSignal.publication_id == first.id))
    }
    assert all(app_db_session.get(ArtifactPassageLanguageSignal, sid).language_signal_artifact_version != "signals_v2_test" for sid in old_signal_ids)


def test_alignment_version_bump_creates_new_alignment_and_retrieval_generations(db_session, app_db_session, tmp_path):
    """Section 12.B: bumping `ALIGNMENT_ARTIFACT_VERSION` creates new
    `passage_comparisons` AND `retrieval_contexts` generations (the single
    shared version axis those two families deliberately use, per `labels.py`
    -- see the module docstring there), while language signals and QA chunks
    are reused unchanged."""
    _build_and_feature(db_session, tmp_path, ticker="VSA3")

    first = PublicationBuilder(publication_version="vsa3-v1", include_qa_chunks=True).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason
    counts_before = _artifact_counts(app_db_session)

    with patch("market_documents.publishing.publisher.labels.ALIGNMENT_ARTIFACT_VERSION", "alignment_v2_test"):
        second = PublicationBuilder(publication_version="vsa3-v2", include_qa_chunks=True).build(
            db_session, app_db_session
        )
    assert second.status == PublicationStatus.READY.value, second.failure_reason

    counts_after = _artifact_counts(app_db_session)
    assert counts_after["passage_comparisons"] > counts_before["passage_comparisons"]
    assert counts_after["retrieval_contexts"] > counts_before["retrieval_contexts"]
    assert counts_after["passage_language_signals"] == counts_before["passage_language_signals"]
    assert counts_after["qa_chunks"] == counts_before["qa_chunks"]


def test_qa_chunking_version_bump_creates_new_qa_generation_only(db_session, app_db_session, tmp_path):
    """Section 12.C: bumping `QA_CHUNKING_ARTIFACT_VERSION` creates a new QA
    generation only."""
    _build_and_feature(db_session, tmp_path, ticker="VSA4")

    first = PublicationBuilder(publication_version="vsa4-v1", include_qa_chunks=True).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason
    counts_before = _artifact_counts(app_db_session)

    with patch("market_documents.publishing.publisher.labels.QA_CHUNKING_ARTIFACT_VERSION", "qa_chunk_v2_test"):
        second = PublicationBuilder(publication_version="vsa4-v2", include_qa_chunks=True).build(
            db_session, app_db_session
        )
    assert second.status == PublicationStatus.READY.value, second.failure_reason

    counts_after = _artifact_counts(app_db_session)
    assert counts_after["qa_chunks"] > counts_before["qa_chunks"]
    assert counts_after["passage_comparisons"] == counts_before["passage_comparisons"]
    assert counts_after["retrieval_contexts"] == counts_before["retrieval_contexts"]
    assert counts_after["passage_language_signals"] == counts_before["passage_language_signals"]


def test_immutability_p1_unaffected_by_p2_family_version_bump(db_session, app_db_session, tmp_path):
    """Section 13: P1 -> generation V1, P2 -> generation V2 for one family.
    After P2's build, P1 must still resolve exactly to V1 -- no P1 shared
    row updated, no P1 membership FK changed."""
    _build_and_feature(db_session, tmp_path, ticker="VSA5")

    first = PublicationBuilder(publication_version="vsa5-v1", include_qa_chunks=True).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason

    first_signal_rows_before = list(
        app_db_session.scalars(select(AppPassageLanguageSignal).where(AppPassageLanguageSignal.publication_id == first.id))
    )
    first_signal_artifact_ids_before = {r.language_signal_artifact_id for r in first_signal_rows_before}
    first_signal_content_before = {
        sid: (
            lambda a: (a.raw_count, a.adjusted_count, a.content_hash)
        )(app_db_session.get(ArtifactPassageLanguageSignal, sid))
        for sid in first_signal_artifact_ids_before
    }

    with patch("market_documents.publishing.publisher.labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION", "signals_v2_test"):
        second = PublicationBuilder(publication_version="vsa5-v2", include_qa_chunks=True).build(
            db_session, app_db_session
        )
    assert second.status == PublicationStatus.READY.value, second.failure_reason

    first_signal_rows_after = list(
        app_db_session.scalars(select(AppPassageLanguageSignal).where(AppPassageLanguageSignal.publication_id == first.id))
    )
    first_signal_artifact_ids_after = {r.language_signal_artifact_id for r in first_signal_rows_after}
    assert first_signal_artifact_ids_after == first_signal_artifact_ids_before, "P1's membership FK must not change"

    for sid in first_signal_artifact_ids_after:
        artifact = app_db_session.get(ArtifactPassageLanguageSignal, sid)
        assert artifact.language_signal_artifact_version != "signals_v2_test"
        assert (artifact.raw_count, artifact.adjusted_count, artifact.content_hash) == first_signal_content_before[sid]

    second_signal_artifact_ids = {
        r.language_signal_artifact_id
        for r in app_db_session.scalars(select(AppPassageLanguageSignal).where(AppPassageLanguageSignal.publication_id == second.id))
    }
    assert second_signal_artifact_ids.isdisjoint(first_signal_artifact_ids_after)
    for sid in second_signal_artifact_ids:
        assert app_db_session.get(ArtifactPassageLanguageSignal, sid).language_signal_artifact_version == "signals_v2_test"


def test_rollback_resolves_correct_generation_via_current_views(db_session, app_db_session, tmp_path):
    """Section 14: build P1, promote, build P2 (bumped language-signal
    version), promote, activate/rollback P1, verify `app.current_passage_
    language_signals` resolves back to P1's generation; then reactivate P2
    and verify again.

    Known gap (documented, not fixed by this track): `activate_publication`
    refuses a non-READY target, so it cannot itself reactivate P1 once P2's
    promotion has moved P1 to SUPERSEDED -- there is no dedicated "rollback"
    function yet (production rollback, per docs/7e3-fresh-neon-production-
    cutover.md, has so far always meant reverting `APP_READONLY_DATABASE_URL`
    to a different Neon project, never reactivating a SUPERSEDED row in the
    SAME database). This test exercises the actual read path a rollback
    depends on -- `ApplicationState.active_publication_id` flipped directly,
    then read back through `app.current_*` -- without asserting a rollback
    CLI/function exists."""
    from sqlalchemy import text

    from market_documents.publishing.models import ApplicationState

    _build_and_feature(db_session, tmp_path, ticker="VSA6")

    first = PublicationBuilder(publication_version="vsa6-v1", include_qa_chunks=False).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason
    activate_publication(app_db_session, first.id)

    with patch("market_documents.publishing.publisher.labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION", "signals_v2_test"):
        second = PublicationBuilder(publication_version="vsa6-v2", include_qa_chunks=False).build(
            db_session, app_db_session
        )
    assert second.status == PublicationStatus.READY.value, second.failure_reason
    activate_publication(app_db_session, second.id)

    def _active_language_signal_versions() -> set[str | None]:
        rows = app_db_session.execute(
            text(
                "SELECT DISTINCT s.language_signal_artifact_version "
                "FROM app.current_passage_language_signals v "
                "JOIN app_artifacts.passage_language_signals s ON s.id = v.language_signal_artifact_id"
            )
        ).all()
        return {r[0] for r in rows}

    def _set_active(publication_id) -> None:
        state = app_db_session.get(ApplicationState, "active")
        state.active_publication_id = publication_id
        app_db_session.flush()

    active_versions_p2 = _active_language_signal_versions()
    assert active_versions_p2 == {"signals_v2_test"}

    _set_active(first.id)
    active_versions_p1 = _active_language_signal_versions()
    assert "signals_v2_test" not in active_versions_p1

    _set_active(second.id)
    active_versions_p2_again = _active_language_signal_versions()
    assert active_versions_p2_again == {"signals_v2_test"}


def test_gc_removes_only_unreferenced_artifact_generations(db_session, app_db_session, tmp_path):
    """Section 15: active publication's artifact is never deleted; rollback
    publication's artifact is never deleted; an unreferenced old generation
    IS removed once cleanup_publications has removed the referencing
    publication's own thin rows; GC order is cleanup-then-artifact-GC."""
    _build_and_feature(db_session, tmp_path, ticker="VSA7")

    first = PublicationBuilder(publication_version="vsa7-v1", include_qa_chunks=False).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason

    with patch("market_documents.publishing.publisher.labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION", "signals_v2_test"):
        second = PublicationBuilder(publication_version="vsa7-v2", include_qa_chunks=False).build(
            db_session, app_db_session
        )
    assert second.status == PublicationStatus.READY.value, second.failure_reason

    v1_count = app_db_session.scalar(
        select(func.count()).select_from(ArtifactPassageLanguageSignal).where(
            ArtifactPassageLanguageSignal.language_signal_artifact_version != "signals_v2_test"
        )
    )
    assert v1_count > 0

    # Dry-run before any cleanup: both publications retained -> nothing orphaned.
    dry_run_result = gc_orphaned_artifact_rows(app_db_session, dry_run=True)
    assert dry_run_result["passage_language_signals"] == 0

    # keep=1 retains only the most recent (second); first is deleted.
    removed = cleanup_publications(app_db_session, keep=1, dry_run=False)
    assert {p.id for p in removed} == {first.id}

    gc_result = gc_orphaned_artifact_rows(app_db_session, dry_run=False)
    assert gc_result["passage_language_signals"] == v1_count

    remaining_versions = set(
        app_db_session.scalars(select(ArtifactPassageLanguageSignal.language_signal_artifact_version))
    )
    assert remaining_versions == {"signals_v2_test"}


def test_content_hash_mismatch_raises_loudly(db_session, app_db_session, tmp_path):
    """Section 8: if an existing generation's stored content no longer
    matches what a build would compute under the SAME identity+version (a
    stand-in here for "a developer changed generation logic without
    bumping the version"), the build must fail loudly rather than silently
    reuse or overwrite the row."""
    _build_and_feature(db_session, tmp_path, ticker="VSA8")

    first = PublicationBuilder(publication_version="vsa8-v1", include_qa_chunks=False).build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason

    artifact = app_db_session.scalars(select(ArtifactPassageComparison)).first()
    assert artifact is not None
    artifact.content_hash = "deliberately-corrupted-hash"
    app_db_session.flush()

    with pytest.raises(RuntimeError, match="content hash mismatch"):
        PublicationBuilder(publication_version="vsa8-v2", include_qa_chunks=False).build(db_session, app_db_session)
