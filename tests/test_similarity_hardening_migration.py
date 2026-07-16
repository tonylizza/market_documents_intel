from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

REPO_ROOT = Path(__file__).resolve().parents[1]
M3_REVISION = "d8118d0f8412"

NEW_COLUMNS = {"diff_mode", "diff_duration_ms"}


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def _column_names(engine, table_name: str) -> set[str]:
    with engine.connect() as conn:
        return {col["name"] for col in inspect(conn).get_columns(table_name)}


def _enum_names(engine) -> set[str]:
    with engine.connect() as conn:
        result = conn.exec_driver_sql("SELECT typname FROM pg_type WHERE typtype = 'e'")
        return {row[0] for row in result}


def test_hardening_migration_adds_diff_mode_columns(engine):
    columns = _column_names(engine, "document_similarities")
    assert NEW_COLUMNS.issubset(columns)
    assert "diff_mode" in _enum_names(engine)


def test_hardening_migration_is_reversible_to_milestone_3(engine):
    """Downgrading to the M3 head must remove only the diff-mode additions,
    never touch M1/M2/M3 tables, and be re-upgradable cleanly.
    """
    cfg = _alembic_config()

    command.downgrade(cfg, M3_REVISION)
    columns_after_downgrade = _column_names(engine, "document_similarities")
    assert not NEW_COLUMNS.intersection(columns_after_downgrade)
    assert "diff_mode" not in _enum_names(engine)
    # Pre-existing document_similarities columns from M3 remain untouched.
    assert "lexical_cosine_similarity" in columns_after_downgrade
    assert "quality_status" in columns_after_downgrade

    command.upgrade(cfg, "head")
    columns_after_upgrade = _column_names(engine, "document_similarities")
    assert NEW_COLUMNS.issubset(columns_after_upgrade)
    assert "diff_mode" in _enum_names(engine)


def test_hardening_migration_preserves_existing_data(engine):
    """A round-trip downgrade/upgrade must not touch pre-existing rows in
    unrelated tables (companies), proving the migration is additive-only.
    """
    from sqlalchemy.orm import Session

    from market_documents.models.company import Company

    with Session(engine) as session:
        company = Company(ticker="MHZZZ", company_name="Hardening Migration Test Co")
        session.add(company)
        session.commit()
        company_id = company.id

    try:
        cfg = _alembic_config()
        command.downgrade(cfg, M3_REVISION)
        command.upgrade(cfg, "head")

        with Session(engine) as session:
            assert session.get(Company, company_id) is not None
    finally:
        with Session(engine) as session:
            obj = session.get(Company, company_id)
            if obj is not None:
                session.delete(obj)
                session.commit()
