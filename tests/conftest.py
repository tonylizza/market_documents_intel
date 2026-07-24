import os
from pathlib import Path

# Point the whole test session at a dedicated test database before any
# market_documents module is imported, so get_settings()/get_engine() (used
# by both services and the CLI) resolve to it consistently. Port is
# overridable via POSTGRES_PORT (defaulting to the project's normal
# docker-compose port) so a locally-conflicting, unrelated container on the
# default port doesn't force editing this file.
_POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5433")
TEST_DATABASE_URL = (
    f"postgresql+psycopg://market_documents:market_documents@localhost:{_POSTGRES_PORT}/market_documents_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import psycopg  # noqa: E402
import pytest  # noqa: E402
from psycopg import sql  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_NAME = "market_documents_test"
ADMIN_DSN = f"postgresql://market_documents:market_documents@localhost:{_POSTGRES_PORT}/postgres"


def _ensure_test_database_exists() -> None:
    conn = psycopg.connect(ADMIN_DSN, autocommit=True)
    try:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        ).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB_NAME)))
    finally:
        conn.close()


@pytest.fixture(scope="session")
def engine():
    _ensure_test_database_exists()

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(cfg, "head")

    eng = create_engine(TEST_DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    connection = engine.connect()
    trans = connection.begin()
    session_factory = sessionmaker(bind=connection, future=True, expire_on_commit=False)
    session: Session = session_factory()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture()
def companies_config_path() -> Path:
    return REPO_ROOT / "config" / "companies.yaml"
