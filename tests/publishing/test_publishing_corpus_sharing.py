"""Track 7E.1: shared, publication-independent passage corpus.

Uses the same `_feature_fixtures.build_ready_pair` real end-to-end fixture
as `test_publishing_retrieval.py`. These tests exercise the actual storage-
sharing behavior the milestone is about -- two DIFFERENT publications
(different `publication_version`, never a rebuild-same-version case, which
`test_publishing_retrieval.py` already covers) built from the same
unchanged source data must physically share `app_corpus.*` rows, never
duplicate them, while their own publication-scoped rows stay isolated.
"""

import sys
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _feature_fixtures import build_ready_pair  # noqa: E402

from market_documents.publishing.models import CorpusPassage, CorpusPassageEmbedding
from market_documents.publishing.models import Passage as AppPassage
from market_documents.publishing.models import PublicationStatus, RetrievalContext
from market_documents.publishing.publisher import PublicationBuilder, cleanup_publications, gc_orphaned_corpus_rows
from market_documents.services.feature_extraction import build_features


def _build_and_feature(db_session, ticker: str, **kwargs):
    pair, alignment_outcome, _similarity_outcome = build_ready_pair(db_session, ticker=ticker, **kwargs)
    build_features(db_session, pair)
    db_session.flush()
    return pair, alignment_outcome


def test_two_publications_share_corpus_rows_not_duplicated(db_session, app_db_session):
    """Section 16.A: two publications reference shared immutable data
    correctly; duplicate large rows are not created unnecessarily."""
    _build_and_feature(db_session, ticker="COR1")

    first = PublicationBuilder(publication_version="cor-test-v1").build(db_session, app_db_session)
    assert first.status == PublicationStatus.READY.value, first.failure_reason
    second = PublicationBuilder(publication_version="cor-test-v2").build(db_session, app_db_session)
    assert second.status == PublicationStatus.READY.value, second.failure_reason
    assert first.id != second.id

    first_passages = list(app_db_session.scalars(select(AppPassage).where(AppPassage.publication_id == first.id)))
    second_passages = list(app_db_session.scalars(select(AppPassage).where(AppPassage.publication_id == second.id)))
    assert len(first_passages) == len(second_passages) == 2

    first_source_ids = {p.source_passage_id for p in first_passages}
    second_source_ids = {p.source_passage_id for p in second_passages}
    assert first_source_ids == second_source_ids  # same unchanged source passages

    total_corpus_passages = app_db_session.scalar(select(func.count()).select_from(CorpusPassage))
    total_corpus_embeddings = app_db_session.scalar(select(func.count()).select_from(CorpusPassageEmbedding))
    # Exactly one physical corpus row per distinct source passage -- NOT one
    # per (source passage, publication) pair. If sharing were broken this
    # would be 4 (2 passages x 2 publications), not 2.
    assert total_corpus_passages == 2
    assert total_corpus_embeddings == 2

    # Every RetrievalContext from either publication must resolve to a
    # corpus embedding id that actually exists -- not a per-publication one.
    corpus_embedding_ids = set(app_db_session.scalars(select(CorpusPassageEmbedding.id)))
    for pub_id in (first.id, second.id):
        contexts = list(
            app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == pub_id))
        )
        assert contexts
        for ctx in contexts:
            assert ctx.passage_embedding_id in corpus_embedding_ids


def test_publication_specific_rows_stay_isolated(db_session, app_db_session):
    """Section 16.B: release-specific comparison rows remain publication-
    specific even though the underlying corpus is shared -- `app.passages`
    and `app.retrieval_contexts` still get one full row set per
    publication (they're cheap; only the heavyweight text/vector payload is
    shared)."""
    _build_and_feature(db_session, ticker="COR2")

    first = PublicationBuilder(publication_version="cor-test-v3").build(db_session, app_db_session)
    second = PublicationBuilder(publication_version="cor-test-v4").build(db_session, app_db_session)
    assert first.status == second.status == PublicationStatus.READY.value

    first_passage_ids = {
        p.id for p in app_db_session.scalars(select(AppPassage).where(AppPassage.publication_id == first.id))
    }
    second_passage_ids = {
        p.id for p in app_db_session.scalars(select(AppPassage).where(AppPassage.publication_id == second.id))
    }
    # Different publications -> different `app.passages` primary keys, even
    # though they resolve to the same corpus content.
    assert first_passage_ids.isdisjoint(second_passage_ids)

    first_context_ids = {
        c.id for c in app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == first.id))
    }
    second_context_ids = {
        c.id
        for c in app_db_session.scalars(select(RetrievalContext).where(RetrievalContext.publication_id == second.id))
    }
    assert first_context_ids.isdisjoint(second_context_ids)


def test_cleanup_then_gc_removes_truly_orphaned_corpus_rows(db_session, app_db_session):
    """Section 16.D: deleting a superseded publication does not delete
    shared data still referenced by another publication; `gc_orphaned_
    corpus_rows` removes a corpus row only once NOTHING references it."""
    from market_documents.publishing.models import Publication

    _build_and_feature(db_session, ticker="COR3")

    first = PublicationBuilder(publication_version="cor-test-v5").build(db_session, app_db_session)
    second = PublicationBuilder(publication_version="cor-test-v6").build(db_session, app_db_session)
    assert first.status == second.status == PublicationStatus.READY.value

    total_before = app_db_session.scalar(select(func.count()).select_from(CorpusPassageEmbedding))
    assert total_before == 2

    # `keep=1` (neither is ACTIVE) retains only the most recently completed
    # -- `second` -- and deletes `first`. `second` still references the same
    # corpus rows `first` used, so they must survive.
    removed = cleanup_publications(app_db_session, keep=1, dry_run=False)
    assert {p.id for p in removed} == {first.id}
    assert app_db_session.get(Publication, second.id) is not None

    dry_run_result = gc_orphaned_corpus_rows(app_db_session, dry_run=True)
    assert dry_run_result == {"passages": 0, "passage_embeddings": 0}  # `second` still references everything
    total_after_first_cleanup = app_db_session.scalar(select(func.count()).select_from(CorpusPassageEmbedding))
    assert total_after_first_cleanup == total_before  # nothing removed -- still referenced by `second`

    # Now remove `second` too -- nothing references the corpus rows any more.
    removed2 = cleanup_publications(app_db_session, keep=0, dry_run=False)
    assert {p.id for p in removed2} == {second.id}

    gc_result = gc_orphaned_corpus_rows(app_db_session, dry_run=False)
    assert gc_result == {"passages": 2, "passage_embeddings": 2}
    total_after_gc = app_db_session.scalar(select(func.count()).select_from(CorpusPassageEmbedding))
    assert total_after_gc == 0


def test_reproducibility_embedding_matches_corpus_text_hash(db_session, app_db_session):
    """Section 16.E: a publication resolves the exact corpus/vector version
    it was built against -- the embedding's stored `embedding_text_hash`
    still matches a fresh hash of the corpus text it was computed from."""
    from market_documents.publishing.retrieval_contexts import embedding_text_hash

    _build_and_feature(db_session, ticker="COR4")
    publication = PublicationBuilder(publication_version="cor-test-v7").build(db_session, app_db_session)
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason

    passages = list(app_db_session.scalars(select(AppPassage).where(AppPassage.publication_id == publication.id)))
    source_ids = {p.source_passage_id for p in passages}
    corpus_texts = {
        cp.source_passage_id: cp.text
        for cp in app_db_session.scalars(select(CorpusPassage).where(CorpusPassage.source_passage_id.in_(source_ids)))
    }
    embeddings = list(
        app_db_session.scalars(
            select(CorpusPassageEmbedding).where(CorpusPassageEmbedding.source_passage_id.in_(source_ids))
        )
    )
    assert embeddings
    for e in embeddings:
        assert e.embedding_text_hash == embedding_text_hash(corpus_texts[e.source_passage_id])
