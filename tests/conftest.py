import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _dotenv_postgres_port(env_path: Path) -> str | None:
    """Minimal, dependency-free single-key ``.env`` reader -- avoids adding
    python-dotenv as a direct test dependency (it is currently only a
    transitive dependency of pydantic-settings) just for this one lookup."""
    if not env_path.is_file():
        return None
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "POSTGRES_PORT":
            return value.strip().strip("'\"")
    return None


# Point the whole test session at a dedicated test database before any
# market_documents module is imported, so get_settings()/get_engine() (used
# by both services and the CLI) resolve to it consistently.
#
# Port precedence: an explicit POSTGRES_PORT environment variable always
# wins; otherwise fall back to this repository's own `.env` (the port this
# project's docker-compose actually publishes locally); otherwise fall back
# to docker-compose.yml's own unset-port default (5432, matching
# Settings.database_url's default). Previously this hardcoded "5433"
# independently of both `.env` and docker-compose.yml -- on a machine where
# an unrelated project's Postgres container happens to occupy port 5433,
# tests would target that container's `market_documents_test` database
# instead of this project's own dev database, either silently or (if
# credentials merely differ) with a confusing auth failure that gives no
# hint the wrong database was ever in play.
_POSTGRES_PORT = os.environ.get("POSTGRES_PORT") or _dotenv_postgres_port(REPO_ROOT / ".env") or "5432"
TEST_DB_NAME = "market_documents_test"
# An explicit TEST_DATABASE_URL always wins; otherwise fall back to the
# derived default (unchanged behavior). Milestone 7A.1 needs this to
# actually be overridable so a second, application-database test fixture
# can follow the identical pattern without hardcoding a port/name pair
# twice.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or (
    f"postgresql+psycopg://market_documents:market_documents@localhost:{_POSTGRES_PORT}/{TEST_DB_NAME}"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

TEST_APP_DB_NAME = "market_documents_app_test"
TEST_APP_DATABASE_URL = os.environ.get("TEST_APP_DATABASE_URL") or (
    f"postgresql+psycopg://market_documents:market_documents@localhost:{_POSTGRES_PORT}/{TEST_APP_DB_NAME}"
)
os.environ["APP_DATABASE_URL"] = TEST_APP_DATABASE_URL

import psycopg  # noqa: E402
import pytest  # noqa: E402
from psycopg import sql  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

ADMIN_DSN = f"postgresql://market_documents:market_documents@localhost:{_POSTGRES_PORT}/postgres"


def _ensure_database_exists(db_name: str) -> None:
    conn = psycopg.connect(ADMIN_DSN, autocommit=True)
    try:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    finally:
        conn.close()


def _ensure_test_database_exists() -> None:
    _ensure_database_exists(TEST_DB_NAME)


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


@pytest.fixture(scope="session")
def app_engine():
    """Milestone 7A.1: mirrors `engine` above exactly, but for the
    application/publication-layer test database and its own (separate)
    Alembic environment (`alembic_app.ini` / `migrations_app/`)."""
    _ensure_database_exists(TEST_APP_DB_NAME)

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "alembic_app.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations_app"))
    cfg.set_main_option("sqlalchemy.url", TEST_APP_DATABASE_URL)
    command.upgrade(cfg, "head")

    eng = create_engine(TEST_APP_DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def app_db_session(app_engine):
    """Mirrors `db_session` exactly, against the application test database.
    Entirely independent of `db_session` -- a test can request both without
    cross-contamination, since they're two separate physical databases."""
    connection = app_engine.connect()
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
