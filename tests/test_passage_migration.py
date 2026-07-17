from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[1]
M3_5_REVISION = "c9e96ef451f1"

PASSAGE_TABLES = {
    "passage_segmentation_runs",
    "passages",
    "passage_source_blocks",
    "embedding_runs",
    "passage_embeddings",
    "alignment_runs",
    "passage_alignments",
}
PASSAGE_ENUMS = {
    "passage_segmentation_run_status",
    "embedding_run_status",
    "passage_type",
    "alignment_run_status",
    "alignment_status",
    "alignment_type",
    "alignment_confidence",
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


def test_passage_migration_creates_expected_tables(engine):
    assert PASSAGE_TABLES.issubset(_table_names(engine))
    assert PASSAGE_ENUMS.issubset(_enum_names(engine))


def test_passage_migration_is_reversible_to_milestone_3_5(engine):
    """Downgrading to the M3.5 head must remove only the M4 additions,
    never touch M1-M3.5 tables, and be re-upgradable cleanly.
    """
    cfg = _alembic_config()

    command.downgrade(cfg, M3_5_REVISION)
    tables_after_downgrade = _table_names(engine)
    assert not PASSAGE_TABLES.intersection(tables_after_downgrade)
    assert {
        "extraction_runs",
        "pages",
        "text_blocks",
        "narrative_documents",
        "similarity_runs",
        "document_similarities",
    }.issubset(tables_after_downgrade)
    assert not PASSAGE_ENUMS.intersection(_enum_names(engine))

    command.upgrade(cfg, "head")
    tables_after_upgrade = _table_names(engine)
    assert PASSAGE_TABLES.issubset(tables_after_upgrade)
    assert {"similarity_runs", "document_similarities"}.issubset(tables_after_upgrade)


def test_passage_migration_preserves_existing_data(engine):
    """A round-trip downgrade/upgrade must not touch pre-existing M1-M3.5 rows."""
    from market_documents.models.company import Company

    with Session(engine) as session:
        company = Company(ticker="MPZZZ", company_name="Passage Migration Test Co")
        session.add(company)
        session.commit()
        company_id = company.id

    try:
        cfg = _alembic_config()
        command.downgrade(cfg, M3_5_REVISION)
        command.upgrade(cfg, "head")

        with Session(engine) as session:
            assert session.get(Company, company_id) is not None
    finally:
        with Session(engine) as session:
            obj = session.get(Company, company_id)
            if obj is not None:
                session.delete(obj)
                session.commit()


def test_vector_dimension_is_enforced(db_session):
    """The `passage_embeddings.embedding` column must reject the wrong dimension.

    Uses a scratch temp table with the same `vector(384)` type rather than
    the real table, so this checks the pgvector column type itself without
    needing a full Report/ExtractionRun/.../Passage fixture chain to satisfy
    foreign keys.
    """
    from sqlalchemy import text

    from market_documents.models.embedding import EMBEDDING_DIMENSION

    db_session.execute(text(f"CREATE TEMP TABLE test_vector_dim (v vector({EMBEDDING_DIMENSION}))")).close()

    correct = "[" + ",".join(["0.1"] * EMBEDDING_DIMENSION) + "]"
    db_session.execute(text("INSERT INTO test_vector_dim (v) VALUES (:v)"), {"v": correct})

    wrong = "[" + ",".join(["0.1"] * (EMBEDDING_DIMENSION - 1)) + "]"
    with pytest.raises(DataError):
        db_session.execute(text("INSERT INTO test_vector_dim (v) VALUES (:v)"), {"v": wrong})
