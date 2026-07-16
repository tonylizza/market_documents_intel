from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

REPO_ROOT = Path(__file__).resolve().parents[1]
M2_REVISION = "8c622d3ced32"

SIMILARITY_TABLES = {"similarity_runs", "document_similarities"}


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


def _row_count(engine, table_name: str) -> int:
    with engine.connect() as conn:
        return conn.exec_driver_sql(f"SELECT COUNT(*) FROM {table_name}").scalar()


def test_similarity_migration_creates_expected_tables(engine):
    assert SIMILARITY_TABLES.issubset(_table_names(engine))
    assert {"similarity_run_status", "similarity_result_quality"}.issubset(_enum_names(engine))


def test_similarity_migration_is_reversible_to_milestone_2(engine):
    """Downgrading to the Milestone 2 head must remove only the M3 additions,
    never touch M1/M2 tables, and be re-upgradable cleanly.
    """
    cfg = _alembic_config()

    command.downgrade(cfg, M2_REVISION)
    tables_after_downgrade = _table_names(engine)
    assert not SIMILARITY_TABLES.intersection(tables_after_downgrade)
    assert {"extraction_runs", "pages", "text_blocks", "narrative_documents"}.issubset(tables_after_downgrade)
    assert not {"similarity_run_status", "similarity_result_quality"}.intersection(_enum_names(engine))

    command.upgrade(cfg, "head")
    tables_after_upgrade = _table_names(engine)
    assert SIMILARITY_TABLES.issubset(tables_after_upgrade)
    assert {"extraction_runs", "pages", "text_blocks", "narrative_documents"}.issubset(tables_after_upgrade)


def test_similarity_migration_preserves_existing_data(engine):
    """A round-trip downgrade/upgrade must not touch Milestone 1/2 data.

    Uses a real, directly committed row (not the `db_session` fixture's
    rolled-back savepoint) since the point is to prove data survives an
    actual downgrade/upgrade against the database, not just within one
    isolated test transaction.
    """
    from sqlalchemy.orm import Session

    from market_documents.models.company import Company

    with Session(engine) as session:
        company = Company(ticker="MZZZ", company_name="Migration Test Co")
        session.add(company)
        session.commit()
        company_id = company.id

    try:
        row_count_before = _row_count(engine, "companies")

        cfg = _alembic_config()
        command.downgrade(cfg, M2_REVISION)
        command.upgrade(cfg, "head")

        assert _row_count(engine, "companies") == row_count_before
        with Session(engine) as session:
            assert session.get(Company, company_id) is not None
    finally:
        with Session(engine) as session:
            obj = session.get(Company, company_id)
            if obj is not None:
                session.delete(obj)
                session.commit()
