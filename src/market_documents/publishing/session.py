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
