import pytest

from market_documents.publishing.session import SameDatabaseError, assert_distinct_databases

SOURCE = "postgresql+psycopg://user:pw@localhost:5434/market_documents"
TARGET_SAME_HOST_DB = "postgresql+psycopg://other_user:other_pw@localhost:5434/market_documents"
TARGET_DIFFERENT_DB = "postgresql+psycopg://user:pw@localhost:5434/market_documents_app"
TARGET_DIFFERENT_PORT = "postgresql+psycopg://user:pw@localhost:5433/market_documents"


def test_raises_when_same_host_port_database():
    with pytest.raises(SameDatabaseError):
        assert_distinct_databases(SOURCE, TARGET_SAME_HOST_DB, allow_same_database_dev_mode=False)


def test_credentials_do_not_matter_only_host_port_database():
    # Different user/password on the same host/port/database is still the
    # same physical database -- must still raise.
    with pytest.raises(SameDatabaseError):
        assert_distinct_databases(SOURCE, TARGET_SAME_HOST_DB, allow_same_database_dev_mode=False)


def test_allows_when_dev_override_set():
    assert_distinct_databases(SOURCE, TARGET_SAME_HOST_DB, allow_same_database_dev_mode=True)  # no raise


def test_allows_distinct_database_name():
    assert_distinct_databases(SOURCE, TARGET_DIFFERENT_DB, allow_same_database_dev_mode=False)  # no raise


def test_allows_distinct_port():
    assert_distinct_databases(SOURCE, TARGET_DIFFERENT_PORT, allow_same_database_dev_mode=False)  # no raise
