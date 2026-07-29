"""disclosure-change quality fields (review-qualified disclosure-change publication)

Revision ID: app_0006
Revises: app_0005
Create Date: 2026-07-27 16:00:00.000000

Adds four columns to `app.report_comparisons` so a NEEDS_REVIEW-quality
`disclosure_change_score` can still be published (with its own quality made
explicit) instead of being silently withheld. See the Milestone 7A.1
follow-up brief ("review-qualified disclosure-change publication") and
`market_documents.publishing.labels.disclosure_change_score_displayed`.

`app.current_report_comparisons` is a `SELECT t.*` view -- Postgres expands
`*` to an explicit column list at `CREATE`/`CREATE OR REPLACE` time, so
merely adding columns to the base table does NOT make them visible through
the view. This migration must explicitly `CREATE OR REPLACE` the view after
adding the columns (upgrade) and before dropping them (downgrade).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from market_documents.publishing.schema import CURRENT_VIEWS

# revision identifiers, used by Alembic.
revision: str = 'app_0006'
down_revision: Union[str, Sequence[str], None] = 'app_0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VIEW_SQL_BY_NAME = dict(CURRENT_VIEWS)
_REPORT_COMPARISONS_VIEW_SQL = _VIEW_SQL_BY_NAME["current_report_comparisons"]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'report_comparisons',
        sa.Column('disclosure_change_quality', sa.String(length=32), nullable=True),
        schema='app',
    )
    op.add_column(
        'report_comparisons',
        sa.Column('disclosure_change_quality_label', sa.String(length=64), nullable=True),
        schema='app',
    )
    op.add_column(
        'report_comparisons',
        sa.Column('disclosure_change_primary_eligible', sa.Boolean(), nullable=True),
        schema='app',
    )
    op.add_column(
        'report_comparisons',
        sa.Column('disclosure_change_warning', sa.Text(), nullable=True),
        schema='app',
    )
    # Re-expand the view's `SELECT *` to include the four new columns.
    op.execute(_REPORT_COMPARISONS_VIEW_SQL)


def downgrade() -> None:
    """Downgrade schema."""
    # The view's expanded column list currently includes the four columns
    # being dropped -- Postgres refuses to DROP COLUMN while a view depends
    # on it, so the view must be dropped first and recreated afterward
    # (at which point `SELECT *` naturally re-expands to the smaller,
    # pre-migration column set).
    op.execute("DROP VIEW IF EXISTS app.current_report_comparisons;")
    op.drop_column('report_comparisons', 'disclosure_change_warning', schema='app')
    op.drop_column('report_comparisons', 'disclosure_change_primary_eligible', schema='app')
    op.drop_column('report_comparisons', 'disclosure_change_quality_label', schema='app')
    op.drop_column('report_comparisons', 'disclosure_change_quality', schema='app')
    op.execute(_REPORT_COMPARISONS_VIEW_SQL)
