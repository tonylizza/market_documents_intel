"""Application-schema migration lifecycle: upgrade, downgrade, re-upgrade,
and isolation of the app_internal.alembic_version bookkeeping table.

The `app_engine` fixture (tests/conftest.py) already runs `upgrade head`
once per session; this module additionally exercises downgrade/re-upgrade
against that same database, then restores head so later tests relying on
`app_engine`/`app_db_session` still see the full schema.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

REPO_ROOT = Path(__file__).resolve().parents[2]


def _app_alembic_config(app_engine) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic_app.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations_app"))
    cfg.set_main_option("sqlalchemy.url", app_engine.url.render_as_string(hide_password=False))
    return cfg


def test_alembic_version_table_lives_in_app_internal_schema(app_engine):
    with app_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT table_schema FROM information_schema.tables "
                "WHERE table_name = 'alembic_version'"
            )
        ).first()
    assert row is not None
    assert row[0] == "app_internal"


def test_expected_tables_present_at_head(app_engine):
    inspector = inspect(app_engine)
    app_tables = set(inspector.get_table_names(schema="app"))
    expected = {
        "companies",
        "reports",
        "report_comparisons",
        "language_metrics",
        "passages",
        "passage_comparisons",
        "passage_language_signals",
        "discovery_items",
        "metric_definitions",
        "metric_label_thresholds",
        "passage_embeddings",
        "retrieval_contexts",
        "retrieval_context_language_categories",
        "retrieval_context_risk_subcategories",
        "qa_chunks",
        "qa_chunk_passages",
    }
    assert expected <= app_tables

    app_internal_tables = set(inspector.get_table_names(schema="app_internal"))
    assert {"publications", "application_state"} <= app_internal_tables


def test_expected_views_present_at_head(app_engine):
    inspector = inspect(app_engine)
    views = set(inspector.get_view_names(schema="app"))
    assert {
        "current_companies",
        "current_reports",
        "current_report_comparisons",
        "current_language_metrics",
        "current_passages",
        "current_passage_comparisons",
        "current_passage_language_signals",
        "current_discovery_items",
        "current_passage_embeddings",
        "current_retrieval_contexts",
        "current_retrieval_context_language_categories",
        "current_retrieval_context_risk_subcategories",
        "current_qa_chunks",
        "current_qa_chunk_passages",
        "current_qa_chunk_vectors",
    } <= views


def test_app_artifacts_tables_present_at_head(app_engine):
    inspector = inspect(app_engine)
    artifact_tables = set(inspector.get_table_names(schema="app_artifacts"))
    assert {
        "passage_comparisons",
        "retrieval_contexts",
        "retrieval_context_language_categories",
        "retrieval_context_risk_subcategories",
        "passage_language_signals",
        "qa_chunks",
        "qa_chunk_passages",
    } <= artifact_tables

    columns = {c["name"] for c in inspector.get_columns("publications", schema="app_internal")}
    assert {
        "alignment_artifact_version",
        "language_signal_artifact_version",
        "qa_chunking_artifact_version",
    } <= columns


def test_disclosure_change_quality_columns_present_at_head(app_engine):
    inspector = inspect(app_engine)
    columns = {c["name"] for c in inspector.get_columns("report_comparisons", schema="app")}
    assert {
        "disclosure_change_quality",
        "disclosure_change_quality_label",
        "disclosure_change_primary_eligible",
        "disclosure_change_warning",
    } <= columns


def test_app_0006_downgrade_to_app_0005_and_reupgrade(app_engine):
    cfg = _app_alembic_config(app_engine)
    try:
        command.downgrade(cfg, "app_0005")

        inspector = inspect(app_engine)
        columns = {c["name"] for c in inspector.get_columns("report_comparisons", schema="app")}
        assert "disclosure_change_quality" not in columns
        # The view must still exist (re-expanded to the smaller column set),
        # not left dangling from the DROP VIEW in downgrade().
        views = set(inspector.get_view_names(schema="app"))
        assert "current_report_comparisons" in views

        command.upgrade(cfg, "head")

        inspector = inspect(app_engine)
        columns = {c["name"] for c in inspector.get_columns("report_comparisons", schema="app")}
        assert "disclosure_change_quality" in columns
        view_columns = {c["name"] for c in inspector.get_columns("current_report_comparisons", schema="app")}
        assert "disclosure_change_quality" in view_columns
    finally:
        command.upgrade(cfg, "head")


def test_app_0007_downgrade_to_app_0006_and_reupgrade(app_engine):
    cfg = _app_alembic_config(app_engine)
    try:
        command.downgrade(cfg, "app_0006")

        inspector = inspect(app_engine)
        app_tables = set(inspector.get_table_names(schema="app"))
        assert "passage_embeddings" not in app_tables
        assert "retrieval_contexts" not in app_tables
        views = set(inspector.get_view_names(schema="app"))
        assert "current_passage_embeddings" not in views
        assert "current_retrieval_contexts" not in views
        # pgvector extension itself is left installed on downgrade (see the
        # migration's downgrade() docstring) -- it must not be dropped.
        with app_engine.connect() as conn:
            row = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            ).first()
        assert row is not None

        command.upgrade(cfg, "head")

        inspector = inspect(app_engine)
        app_tables = set(inspector.get_table_names(schema="app"))
        assert {
            "passage_embeddings",
            "retrieval_contexts",
            "retrieval_context_language_categories",
            "retrieval_context_risk_subcategories",
        } <= app_tables
        views = set(inspector.get_view_names(schema="app"))
        assert {
            "current_passage_embeddings",
            "current_retrieval_contexts",
            "current_retrieval_context_language_categories",
            "current_retrieval_context_risk_subcategories",
        } <= views
    finally:
        command.upgrade(cfg, "head")


def test_app_0008_downgrade_to_app_0007_and_reupgrade(app_engine):
    cfg = _app_alembic_config(app_engine)
    try:
        command.downgrade(cfg, "app_0007")

        inspector = inspect(app_engine)
        app_tables = set(inspector.get_table_names(schema="app"))
        assert "qa_chunks" not in app_tables
        assert "qa_chunk_passages" not in app_tables
        views = set(inspector.get_view_names(schema="app"))
        assert "current_qa_chunks" not in views
        assert "current_qa_chunk_passages" not in views
        columns = {c["name"] for c in inspector.get_columns("publications", schema="app_internal")}
        assert "qa_chunk_count" not in columns
        assert "qa_chunk_passage_mapping_count" not in columns
        # app.passage_embeddings (app_0007) is untouched by downgrading past
        # app_0008 -- 7B.2 is purely additive.
        assert "passage_embeddings" in app_tables

        command.upgrade(cfg, "head")

        inspector = inspect(app_engine)
        app_tables = set(inspector.get_table_names(schema="app"))
        assert {"qa_chunks", "qa_chunk_passages"} <= app_tables
        views = set(inspector.get_view_names(schema="app"))
        assert {"current_qa_chunks", "current_qa_chunk_passages"} <= views
        columns = {c["name"] for c in inspector.get_columns("publications", schema="app_internal")}
        assert {"qa_chunk_count", "qa_chunk_passage_mapping_count"} <= columns
    finally:
        command.upgrade(cfg, "head")


def test_app_0014_downgrade_to_app_0013_and_reupgrade(app_engine):
    cfg = _app_alembic_config(app_engine)
    try:
        command.downgrade(cfg, "app_0013")

        inspector = inspect(app_engine)
        assert "passage_comparisons" not in inspector.get_table_names(schema="app_artifacts")
        columns = {c["name"] for c in inspector.get_columns("passage_comparisons", schema="app")}
        assert "alignment_artifact_id" not in columns
        pub_columns = {c["name"] for c in inspector.get_columns("publications", schema="app_internal")}
        assert "alignment_artifact_version" not in pub_columns
        view_columns = {c["name"] for c in inspector.get_columns("current_passage_comparisons", schema="app")}
        assert "alignment_artifact_id" not in view_columns

        command.upgrade(cfg, "head")

        inspector = inspect(app_engine)
        assert "passage_comparisons" in inspector.get_table_names(schema="app_artifacts")
        columns = {c["name"] for c in inspector.get_columns("passage_comparisons", schema="app")}
        assert "alignment_artifact_id" in columns
        view_columns = {c["name"] for c in inspector.get_columns("current_passage_comparisons", schema="app")}
        assert "alignment_artifact_id" in view_columns
    finally:
        command.upgrade(cfg, "head")


_APP_0015_COLUMNS = {
    "feature_eligible_primary_words_earlier",
    "financial_condition_hits_later",
    "uncertainty_hits_earlier",
    "financial_condition_topic_change",
    "governance_topic_change",
    "uncertainty_topic_change",
    "governance_count_change_per_1000",
    "uncertainty_change_consistency_ratio",
    "financial_condition_largest_passage_share",
    "governance_supporting_hits",
    "positive_rate_change",
    "negative_rate_change",
}


def test_app_0015_downgrade_to_app_0014_and_reupgrade(app_engine):
    cfg = _app_alembic_config(app_engine)
    try:
        command.downgrade(cfg, "app_0014")

        inspector = inspect(app_engine)
        columns = {c["name"] for c in inspector.get_columns("report_comparisons", schema="app")}
        assert not (_APP_0015_COLUMNS & columns)
        view_columns = {c["name"] for c in inspector.get_columns("current_report_comparisons", schema="app")}
        assert not (_APP_0015_COLUMNS & view_columns)

        command.upgrade(cfg, "head")

        inspector = inspect(app_engine)
        columns = {c["name"] for c in inspector.get_columns("report_comparisons", schema="app")}
        assert _APP_0015_COLUMNS <= columns
        # The SELECT t.* view must be re-expanded to expose the new columns.
        view_columns = {c["name"] for c in inspector.get_columns("current_report_comparisons", schema="app")}
        assert _APP_0015_COLUMNS <= view_columns
    finally:
        command.upgrade(cfg, "head")


def test_downgrade_to_base_and_reupgrade_to_head(app_engine):
    cfg = _app_alembic_config(app_engine)
    try:
        command.downgrade(cfg, "base")

        inspector = inspect(app_engine)
        assert inspector.get_table_names(schema="app") == []

        command.upgrade(cfg, "head")

        inspector = inspect(app_engine)
        assert "report_comparisons" in inspector.get_table_names(schema="app")
    finally:
        # Always leave the shared session-scoped engine at head for any
        # other test module using the app_engine/app_db_session fixtures.
        command.upgrade(cfg, "head")


def test_app_0016_downgrade_to_app_0015_and_reupgrade(app_engine):
    cfg = _app_alembic_config(app_engine)
    try:
        command.downgrade(cfg, "app_0015")

        inspector = inspect(app_engine)
        columns = {
            c["name"]: c for c in inspector.get_columns("passage_language_signals", schema="app_artifacts")
        }
        assert "source_passage_alignment_id" not in columns
        assert columns["source_signal_id"]["nullable"] is False
        qa_indexes = {i["name"] for i in inspector.get_indexes("qa_chunks", schema="app")}
        assert "ix_app_qa_chunks_artifact_publication" not in qa_indexes
        assert "current_qa_chunk_vectors" not in set(inspector.get_view_names(schema="app"))

        command.upgrade(cfg, "head")

        inspector = inspect(app_engine)
        columns = {
            c["name"]: c for c in inspector.get_columns("passage_language_signals", schema="app_artifacts")
        }
        assert {"source_passage_alignment_id", "source_passage_id"} <= set(columns)
        assert columns["source_signal_id"]["nullable"] is True
        signal_indexes = {
            i["name"]: i for i in inspector.get_indexes("passage_language_signals", schema="app_artifacts")
        }
        assert signal_indexes["uq_app_artifacts_passage_language_signals_alignment_scope"]["unique"]
        assert signal_indexes["uq_app_artifacts_passage_language_signals_scope"]["unique"]
        qa_indexes = {i["name"] for i in inspect(app_engine).get_indexes("qa_chunks", schema="app")}
        assert "ix_app_qa_chunks_artifact_publication" in qa_indexes
        assert "current_qa_chunk_vectors" in set(inspect(app_engine).get_view_names(schema="app"))
    finally:
        command.upgrade(cfg, "head")


def test_app_0016_downgrade_refuses_while_signals_v2_rows_exist(app_engine):
    import uuid

    import pytest

    cfg = _app_alembic_config(app_engine)
    row_id = uuid.uuid4()
    with app_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_artifacts.passage_language_signals (id, source_passage_alignment_id, "
                "report_side, category, subcategory, language_signal_artifact_version, raw_count, "
                "adjusted_count, is_introduced, is_removed, is_retained, content_hash) VALUES "
                "(:id, :aid, 'EARLIER', 'uncertainty', NULL, 'signals_v2', 1, 1, false, false, true, 'h')"
            ),
            {"id": row_id, "aid": uuid.uuid4()},
        )
    try:
        with pytest.raises(RuntimeError, match="app_0016 downgrade refused"):
            command.downgrade(cfg, "app_0015")
    finally:
        with app_engine.begin() as conn:
            conn.execute(text("DELETE FROM app_artifacts.passage_language_signals WHERE id = :id"), {"id": row_id})
        command.upgrade(cfg, "head")


def test_signal_artifact_identity_check_constraint(app_engine):
    import uuid

    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError, match="ck_app_artifacts_passage_language_signals_identity"):
        with app_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO app_artifacts.passage_language_signals (id, report_side, category, "
                    "language_signal_artifact_version, raw_count, adjusted_count, is_introduced, is_removed, "
                    "is_retained, content_hash) VALUES "
                    "(:id, 'EARLIER', 'uncertainty', 'signals_v2', 1, 1, false, false, true, 'h')"
                ),
                {"id": uuid.uuid4()},
            )
