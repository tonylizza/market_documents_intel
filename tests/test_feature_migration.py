from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
M4_REVISION = "ba39585395d7"

FEATURE_TABLES = {"feature_runs", "report_pair_features"}
FEATURE_ENUMS = {"feature_run_status", "feature_quality"}


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


def test_feature_migration_creates_expected_tables(engine):
    assert FEATURE_TABLES.issubset(_table_names(engine))
    assert FEATURE_ENUMS.issubset(_enum_names(engine))


def test_feature_migration_is_reversible_to_milestone_4(engine):
    """Downgrading to the M4 head must remove only the M5 additions, never
    touch M1-M4 tables or the shared `similarity_result_quality` enum, and
    be re-upgradable cleanly."""
    cfg = _alembic_config()

    command.downgrade(cfg, M4_REVISION)
    tables_after_downgrade = _table_names(engine)
    assert not FEATURE_TABLES.intersection(tables_after_downgrade)
    assert {
        "passages",
        "alignment_runs",
        "passage_alignments",
        "similarity_runs",
        "document_similarities",
    }.issubset(tables_after_downgrade)
    enums_after_downgrade = _enum_names(engine)
    assert not FEATURE_ENUMS.intersection(enums_after_downgrade)
    # The reused M3 enum must survive the M5 downgrade untouched.
    assert "similarity_result_quality" in enums_after_downgrade

    command.upgrade(cfg, "head")
    tables_after_upgrade = _table_names(engine)
    assert FEATURE_TABLES.issubset(tables_after_upgrade)
    assert {"passages", "alignment_runs", "passage_alignments"}.issubset(tables_after_upgrade)


def test_feature_migration_preserves_existing_data(engine):
    """A round-trip downgrade/upgrade must not touch pre-existing M1-M4 rows."""
    from market_documents.models.company import Company

    with Session(engine) as session:
        company = Company(ticker="MFZZZ", company_name="Feature Migration Test Co")
        session.add(company)
        session.commit()
        company_id = company.id

    try:
        cfg = _alembic_config()
        command.downgrade(cfg, M4_REVISION)
        command.upgrade(cfg, "head")

        with Session(engine) as session:
            assert session.get(Company, company_id) is not None
    finally:
        with Session(engine) as session:
            obj = session.get(Company, company_id)
            if obj is not None:
                session.delete(obj)
                session.commit()
