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
    cfg.set_main_option("sqlalchemy.url", str(app_engine.url))
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
    } <= views


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
