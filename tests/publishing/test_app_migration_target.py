"""Track 7F.10: `publish app-init --target-database-url` must migrate the
database it names, never silently the one `APP_DATABASE_URL` points at.

Before 7F.10, `migrations_app/env.py` unconditionally overwrote
`sqlalchemy.url` with `Settings.app_database_url`, so the explicit target
was ignored (7F.9 accidentally upgraded the dev database this way). These
tests use two throwaway databases so the "other" database's untouched state
is directly observable.
"""

import os

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, inspect, text
from typer.testing import CliRunner

from market_documents.cli.publish import app as publish_app
from market_documents.publishing.session import (
    ALEMBIC_PLACEHOLDER_URL,
    describe_database_target,
    resolve_app_migration_url,
)

# Captured at import time: tests/conftest.py has already pointed
# APP_DATABASE_URL at the test app database; the fixture below overrides it.
TEST_APP_DATABASE_URL = os.environ["APP_DATABASE_URL"]
ADMIN_DSN = TEST_APP_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://").rsplit("/", 1)[0] + "/postgres"

_SOURCE_DB = "market_documents_app_7f10_source_test"
_TARGET_DB = "market_documents_app_7f10_target_test"


def _url_for(db_name: str) -> str:
    return TEST_APP_DATABASE_URL.rsplit("/", 1)[0] + f"/{db_name}"


def _recreate(db_name: str) -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(db_name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))


def _drop(db_name: str) -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(db_name)))


def _revision(db_name: str) -> str | None:
    engine = create_engine(_url_for(db_name))
    try:
        with engine.connect() as conn:
            if "alembic_version" not in inspect(conn).get_table_names(schema="app_internal"):
                return None
            return conn.execute(text("SELECT version_num FROM app_internal.alembic_version")).scalar_one()
    finally:
        engine.dispose()


def _schemas(db_name: str) -> set[str]:
    engine = create_engine(_url_for(db_name))
    try:
        with engine.connect() as conn:
            return set(inspect(conn).get_schema_names())
    finally:
        engine.dispose()


@pytest.fixture
def two_blank_databases(monkeypatch):
    _recreate(_SOURCE_DB)
    _recreate(_TARGET_DB)
    # APP_DATABASE_URL (the "dev" database) points at SOURCE throughout.
    monkeypatch.setenv("APP_DATABASE_URL", _url_for(_SOURCE_DB))
    yield
    _drop(_SOURCE_DB)
    _drop(_TARGET_DB)


def test_resolver_precedence_explicit_over_ini_over_settings():
    assert resolve_app_migration_url("postgresql://x/explicit", "postgresql://x/ini", "postgresql://x/settings") == (
        "postgresql://x/explicit"
    )
    assert resolve_app_migration_url(None, "postgresql://x/ini", "postgresql://x/settings") == "postgresql://x/ini"
    assert resolve_app_migration_url(None, ALEMBIC_PLACEHOLDER_URL, "postgresql://x/settings") == (
        "postgresql://x/settings"
    )
    assert resolve_app_migration_url(None, None, "postgresql://x/settings") == "postgresql://x/settings"


def test_describe_database_target_never_prints_credentials():
    described = describe_database_target("postgresql+psycopg://user:s3cret@db.example.com:6543/app?sslmode=require")
    assert described == "db.example.com:6543/app"
    assert "s3cret" not in described and "user" not in described


def test_explicit_target_migrates_target_and_leaves_app_database_url_untouched(two_blank_databases):
    result = CliRunner().invoke(publish_app, ["app-init", "--target-database-url", _url_for(_TARGET_DB)])
    assert result.exit_code == 0, result.output

    # A + C: the explicit target is the one migrated, not replaced by settings.
    assert _revision(_TARGET_DB) is not None
    assert "migration target: localhost:" in result.output
    assert f"/{_TARGET_DB} (from --target-database-url)" in result.output
    assert "market_documents:market_documents@" not in result.output
    # D: the APP_DATABASE_URL (dev/source) database is untouched -- not even
    # the app schemas env.py creates up front exist there.
    assert _revision(_SOURCE_DB) is None
    assert not ({"app", "app_internal", "app_artifacts"} & _schemas(_SOURCE_DB))


def test_default_path_still_uses_app_database_url(two_blank_databases):
    result = CliRunner().invoke(publish_app, ["app-init"])
    assert result.exit_code == 0, result.output

    assert f"/{_SOURCE_DB} (from APP_DATABASE_URL)" in result.output
    assert _revision(_SOURCE_DB) is not None
    assert _revision(_TARGET_DB) is None
    assert not ({"app", "app_internal", "app_artifacts"} & _schemas(_TARGET_DB))
