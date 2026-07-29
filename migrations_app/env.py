from logging.config import fileConfig

import sqlalchemy as sa
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from market_documents.config import get_settings
from market_documents.publishing.models import AppBase
from market_documents.publishing.schema import CREATE_SCHEMAS_SQL

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().app_database_url)

target_metadata = AppBase.metadata

# The app schema's own `alembic_version` table lives inside `app_internal`
# (never `public`), so this history can never collide with the research
# database's `alembic_version` table even when APP_DATABASE_URL and
# DATABASE_URL point at the same physical database (explicit same-database
# dev override -- see `Settings.allow_same_database_dev_mode`).
_VERSION_TABLE_SCHEMA = "app_internal"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=_VERSION_TABLE_SCHEMA,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Alembic cannot create the schema its own version table lives in,
        # so both application schemas are created up front, before the
        # migration context (and its `app_internal.alembic_version` table)
        # is configured.
        for statement in CREATE_SCHEMAS_SQL:
            connection.execute(sa.text(statement))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=_VERSION_TABLE_SCHEMA,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
