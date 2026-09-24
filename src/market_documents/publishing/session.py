"""Application-database session helpers.

Deliberately separate from `market_documents.db.session` (the research
database's module-global lazy engine): the publisher's target database URL
is supplied per-invocation (CLI option or `APP_DATABASE_URL`), not a single
process-wide singleton, since `market-documents publish` commands always
name an explicit target.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


class SameDatabaseError(RuntimeError):
    pass


def _normalized_target(url: str) -> tuple[str | None, int | None, str]:
    parts = urlsplit(url)
    return parts.hostname, parts.port, parts.path.lstrip("/")


def assert_distinct_databases(source_url: str, target_url: str, allow_same_database_dev_mode: bool) -> None:
    """Fail fast unless the research and application database URLs resolve
    to different physical databases, or the explicit development override
    is set. Never silently let a publish run target the research database."""
    if allow_same_database_dev_mode:
        return
    if _normalized_target(source_url) == _normalized_target(target_url):
        raise SameDatabaseError(
            "APP_DATABASE_URL resolves to the same host/port/database as DATABASE_URL. "
            "Publishing would write to the research database. Set a distinct APP_DATABASE_URL, "
            "or explicitly opt in with ALLOW_SAME_DATABASE_DEV_MODE=true for local development."
        )


# `alembic_app.ini`'s literal placeholder -- never a real target.
ALEMBIC_PLACEHOLDER_URL = "driver://user:pass@localhost/dbname"

# Key under which `cli/publish.py` hands an explicit target URL to
# `migrations_app/env.py` via `alembic.config.Config.attributes` (never via
# `sqlalchemy.url`, whose ConfigParser interpolation mangles `%` in
# passwords).
TARGET_URL_ATTRIBUTE = "target_database_url"


def resolve_app_migration_url(explicit_url: str | None, ini_url: str | None, settings_url: str) -> str:
    """Track 7F.10: the application-migration target, in strict precedence:
    an explicit caller-supplied target (`app-init --target-database-url`,
    or a programmatic `Config.attributes` entry) > a real (non-placeholder)
    `sqlalchemy.url` set on the Alembic config > `Settings.app_database_url`
    (`APP_DATABASE_URL`). `migrations_app/env.py` previously overwrote
    `sqlalchemy.url` with the settings value unconditionally, so an explicit
    target was silently ignored and the dev database was migrated instead."""
    if explicit_url:
        return explicit_url
    if ini_url and ini_url != ALEMBIC_PLACEHOLDER_URL:
        return ini_url
    return settings_url


def describe_database_target(url: str) -> str:
    """`host:port/database` for operator confirmation -- never the user,
    password, or query string."""
    host, port, database = _normalized_target(url)
    return f"{host or 'localhost'}:{port or 5432}/{database}"


def create_app_engine(database_url: str):
    return create_engine(database_url, future=True)


@contextmanager
def app_session_scope(database_url: str) -> Iterator[Session]:
    engine = create_app_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()
