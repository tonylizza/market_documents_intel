"""Verifies `app_readonly` can read `app.current_*` views but is denied on
`app_internal` and on raw `app.*` base tables.

Skipped entirely if the `app_readonly`/`app_publisher` roles haven't been
provisioned against the test application database (they're cluster-level,
created via `market-documents publish app-init-roles` /
`scripts/sql/app_roles.sql`, not part of the Alembic schema migrations) --
this is an environment-provisioning step, not something a fresh checkout's
test run should require.
"""

import os

import psycopg
import pytest

_READONLY_TEST_PASSWORD = os.environ.get("APP_READONLY_TEST_PASSWORD")


def _role_exists(app_engine, rolname: str) -> bool:
    with app_engine.connect() as conn:
        row = conn.exec_driver_sql(
            "SELECT 1 FROM pg_roles WHERE rolname = %(name)s", {"name": rolname}
        ).first()
        return row is not None


@pytest.fixture()
def readonly_dsn(app_engine):
    if not _READONLY_TEST_PASSWORD:
        pytest.skip("APP_READONLY_TEST_PASSWORD not set -- app_readonly role not provisioned for this test run")
    if not _role_exists(app_engine, "app_readonly"):
        pytest.skip("app_readonly role does not exist on the test application database")
    url = app_engine.url
    return (
        f"postgresql://app_readonly:{_READONLY_TEST_PASSWORD}@{url.host}:{url.port}/{url.database}"
    )


def test_app_readonly_can_select_current_view(readonly_dsn):
    conn = psycopg.connect(readonly_dsn)
    try:
        conn.execute("SELECT count(*) FROM app.current_report_comparisons")
    finally:
        conn.close()


def test_app_readonly_denied_on_application_state(readonly_dsn):
    conn = psycopg.connect(readonly_dsn)
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count(*) FROM app_internal.application_state")
    finally:
        conn.close()


def test_app_readonly_denied_on_base_table(readonly_dsn):
    conn = psycopg.connect(readonly_dsn)
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT count(*) FROM app.report_comparisons")
    finally:
        conn.close()
