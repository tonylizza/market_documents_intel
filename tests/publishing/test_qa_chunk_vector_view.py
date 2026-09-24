"""Track 7F.10: `app.current_qa_chunk_vectors` (the index-usable QA vector
view) must return exactly what `app.current_qa_chunks` returns for the
active shared-artifact publication (same rows, same embeddings, same
nearest-neighbour order), follow publication activation and rollback, and
let the planner drive the HNSW index on `app_artifacts.qa_chunks`.
"""

import sys
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_versioned_shared_artifacts import _build_and_feature  # noqa: E402

from market_documents.publishing.models import ApplicationState, PublicationStatus
from market_documents.publishing.publisher import PublicationBuilder, activate_publication


def _build(db_session, app_db_session, version: str):
    publication = PublicationBuilder(publication_version=version, include_qa_chunks=True).build(
        db_session, app_db_session
    )
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason
    assert publication.qa_chunk_count > 0
    return publication


def _rows(app_db_session, view: str) -> dict:
    return {
        r[0]: (r[1], r[2], r[3])
        for r in app_db_session.execute(
            text(f"SELECT id, publication_id, embedding::text, text FROM app.{view}")
        ).all()
    }


def _nearest(app_db_session, view: str, query_vector: str) -> list:
    return [
        r[0]
        for r in app_db_session.execute(
            text(f"SELECT id FROM app.{view} ORDER BY embedding <=> CAST(:q AS vector), id LIMIT 50"),
            {"q": query_vector},
        ).all()
    ]


def test_vector_view_matches_current_qa_chunks_and_follows_rollback(db_session, app_db_session, tmp_path):
    _build_and_feature(db_session, tmp_path, ticker="QVV1")
    first = _build(db_session, app_db_session, "qvv-v1")
    activate_publication(app_db_session, first.id)

    via_view = _rows(app_db_session, "current_qa_chunk_vectors")
    assert via_view and via_view == _rows(app_db_session, "current_qa_chunks")
    query_vector = next(iter(via_view.values()))[1]
    assert _nearest(app_db_session, "current_qa_chunk_vectors", query_vector) == _nearest(
        app_db_session, "current_qa_chunks", query_vector
    )

    # A second publication on a different QA generation: the view follows
    # activation, and a rollback resolves back to P1's own generation.
    with patch("market_documents.publishing.publisher.labels.QA_CHUNKING_ARTIFACT_VERSION", "qa_chunk_v2_test"):
        second = _build(db_session, app_db_session, "qvv-v2")
    activate_publication(app_db_session, second.id)
    p2_rows = _rows(app_db_session, "current_qa_chunk_vectors")
    assert {v[0] for v in p2_rows.values()} == {second.id}
    assert p2_rows == _rows(app_db_session, "current_qa_chunks")

    app_db_session.get(ApplicationState, "active").active_publication_id = first.id
    app_db_session.flush()
    assert _rows(app_db_session, "current_qa_chunk_vectors") == via_view


def test_vector_view_nearest_neighbour_plan_uses_artifact_hnsw_index(db_session, app_db_session, tmp_path):
    _build_and_feature(db_session, tmp_path, ticker="QVV2")
    publication = _build(db_session, app_db_session, "qvv2-v1")
    activate_publication(app_db_session, publication.id)
    query_vector = app_db_session.execute(
        text("SELECT embedding::text FROM app.current_qa_chunk_vectors LIMIT 1")
    ).scalar_one()

    # Tiny fixture tables would otherwise always favour a seq scan; this
    # asserts the plan SHAPE is index-capable, which is what the view's
    # single-branch/scalar-subquery design exists to guarantee.
    app_db_session.execute(text("SET LOCAL enable_seqscan = off"))
    app_db_session.execute(text("SET LOCAL enable_sort = off"))
    plan = "\n".join(
        r[0]
        for r in app_db_session.execute(
            text(
                "EXPLAIN SELECT id FROM app.current_qa_chunk_vectors "
                "ORDER BY embedding <=> CAST(:q AS vector) LIMIT 10"
            ),
            {"q": query_vector},
        ).all()
    )
    # The inner lookup index is a cost choice that depends on table size (the
    # real-corpus plan, with `ix_app_qa_chunks_artifact_publication`, is in
    # docs/fresh-neon-cutover-prep-7f10.md); the ordered HNSW scan on the
    # artifact table driving a nested loop is the invariant.
    assert "Index Scan using ix_app_artifacts_qa_chunks_hnsw_cosine on qa_chunks art" in plan, plan
    assert "Nested Loop" in plan, plan
