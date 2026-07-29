"""app.current_* views

Revision ID: app_0005
Revises: app_0004
Create Date: 2026-07-27 14:49:14.509244

Isolated from table DDL history so a future view redefinition (new column,
new filter) never needs to touch the migrations that create the underlying
tables. See `market_documents.publishing.schema` for the SQL and the
security note on how these views expose `app_internal.application_state`'s
effect without granting `app_readonly` any access to `app_internal` itself.
"""
from typing import Sequence, Union

from alembic import op

from market_documents.publishing.schema import CURRENT_VIEWS, DROP_CURRENT_VIEWS_SQL

# revision identifiers, used by Alembic.
revision: str = 'app_0005'
down_revision: Union[str, Sequence[str], None] = 'app_0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for _name, statement in CURRENT_VIEWS:
        op.execute(statement)


def downgrade() -> None:
    """Downgrade schema."""
    for statement in DROP_CURRENT_VIEWS_SQL:
        op.execute(statement)
