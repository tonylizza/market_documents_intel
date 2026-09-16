from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIOR_REVISION = "5c74ac77a25e"

CANONICAL_TABLES = {
    "canonical_extraction_runs",
    "canonical_pages",
    "canonical_blocks",
    "canonical_lines",
    "canonical_spans",
}


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _table_names(engine) -> set[str]:
    with engine.connect() as conn:
        return set(inspect(conn).get_table_names())


def _enum_names(engine) -> set[str]:
    with engine.connect() as conn:
        result = conn.exec_driver_sql("SELECT typname FROM pg_type WHERE typtype = 'e'")
        return {row[0] for row in result}


def test_canonical_migration_creates_expected_tables(engine):
    assert CANONICAL_TABLES.issubset(_table_names(engine))
    assert "canonical_extraction_status" in _enum_names(engine)


def test_canonical_migration_is_reversible(engine):
    """Downgrading to the prior (7C.1) head must remove only the 7C.1a
    additions, never touch schedule/semantic-unit or legacy extraction
    tables, and be re-upgradable cleanly."""
    cfg = _alembic_config()

    command.downgrade(cfg, PRIOR_REVISION)
    tables_after_downgrade = _table_names(engine)
    assert not CANONICAL_TABLES.intersection(tables_after_downgrade)
    assert {"schedule_localization_runs", "semantic_units", "text_blocks", "reports"}.issubset(
        tables_after_downgrade
    )
    assert "canonical_extraction_status" not in _enum_names(engine)

    command.upgrade(cfg, "head")
    tables_after_upgrade = _table_names(engine)
    assert CANONICAL_TABLES.issubset(tables_after_upgrade)
    assert {"schedule_localization_runs", "semantic_units", "text_blocks", "reports"}.issubset(
        tables_after_upgrade
    )
