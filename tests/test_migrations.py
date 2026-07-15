from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _table_names(engine) -> set[str]:
    with engine.connect() as conn:
        return set(inspect(conn).get_table_names())


def test_migration_creates_expected_tables(engine):
    assert {"companies", "reports", "report_pairs"}.issubset(_table_names(engine))


def test_migration_is_reversible(engine):
    """Downgrading to base and back to head must be reproducible."""
    cfg = _alembic_config()

    command.downgrade(cfg, "base")
    assert "reports" not in _table_names(engine)

    command.upgrade(cfg, "head")
    assert {"companies", "reports", "report_pairs"}.issubset(_table_names(engine))
