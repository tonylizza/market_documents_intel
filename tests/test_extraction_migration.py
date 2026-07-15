from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

REPO_ROOT = Path(__file__).resolve().parents[1]
M1_REVISION = "2ff2ba0b15e2"

EXTRACTION_TABLES = {"extraction_runs", "pages", "text_blocks", "narrative_documents"}


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _table_names(engine) -> set[str]:
    with engine.connect() as conn:
        return set(inspect(conn).get_table_names())


def _enum_names(engine) -> set[str]:
    with engine.connect() as conn:
        result = conn.exec_driver_sql(
            "SELECT typname FROM pg_type WHERE typtype = 'e'"
        )
        return {row[0] for row in result}


def test_extraction_migration_creates_expected_tables(engine):
    assert EXTRACTION_TABLES.issubset(_table_names(engine))
    assert {"extraction_status", "extraction_quality", "block_type"}.issubset(_enum_names(engine))


def test_extraction_migration_is_reversible_to_milestone_1(engine):
    """Downgrading to the Milestone 1 head must remove only the M2 additions,
    never touch the initial schema, and be re-upgradable cleanly.
    """
    cfg = _alembic_config()

    command.downgrade(cfg, M1_REVISION)
    tables_after_downgrade = _table_names(engine)
    assert not EXTRACTION_TABLES.intersection(tables_after_downgrade)
    assert {"companies", "reports", "report_pairs"}.issubset(tables_after_downgrade)
    assert not {"extraction_status", "extraction_quality", "block_type"}.intersection(
        _enum_names(engine)
    )

    command.upgrade(cfg, "head")
    tables_after_upgrade = _table_names(engine)
    assert EXTRACTION_TABLES.issubset(tables_after_upgrade)
    assert {"companies", "reports", "report_pairs"}.issubset(tables_after_upgrade)
