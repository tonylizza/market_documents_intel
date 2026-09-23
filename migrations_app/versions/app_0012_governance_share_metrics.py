"""governance share/topic-mix metrics (Track 7F.7a.1: M3-G/M6-G)

Revision ID: app_0012
Revises: app_0011
Create Date: 2026-09-23 00:00:00.000000

Adds five columns to `app.report_comparisons` for the 7F.7a
ADOPT_GOVERNANCE_SHARE_WITH_THRESHOLD methodology: M3-G
(governance_share_earlier/_later/_change + governance_share_change_label)
and M6-G (governance_topic_mix_change, unsigned -- no label column). The
existing `governance_change`/`_label` columns (M1-G) are untouched -- new
metrics get new columns, never overloaded old-column semantics. Exact
mirror of the `app_0011` financial-condition M3/M6b migration, applied to
governance.

`app.current_report_comparisons` is a `SELECT t.*` view -- Postgres expands
`*` to an explicit column list at `CREATE`/`CREATE OR REPLACE` time, so this
migration must explicitly `CREATE OR REPLACE` the view after adding the
columns (upgrade) and before dropping them (downgrade), same pattern as
app_0006/app_0011.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from market_documents.publishing.schema import CURRENT_VIEWS

# revision identifiers, used by Alembic.
revision: str = 'app_0012'
down_revision: Union[str, Sequence[str], None] = 'app_0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VIEW_SQL_BY_NAME = dict(CURRENT_VIEWS)
_REPORT_COMPARISONS_VIEW_SQL = _VIEW_SQL_BY_NAME["current_report_comparisons"]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('report_comparisons', sa.Column('governance_share_earlier', sa.Float(), nullable=True), schema='app')
    op.add_column('report_comparisons', sa.Column('governance_share_later', sa.Float(), nullable=True), schema='app')
    op.add_column('report_comparisons', sa.Column('governance_share_change', sa.Float(), nullable=True), schema='app')
    op.add_column(
        'report_comparisons',
        sa.Column('governance_share_change_label', sa.String(length=64), nullable=True),
        schema='app',
    )
    op.add_column('report_comparisons', sa.Column('governance_topic_mix_change', sa.Float(), nullable=True), schema='app')
    # Re-expand the view's `SELECT *` to include the five new columns.
    op.execute(_REPORT_COMPARISONS_VIEW_SQL)


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres refuses to DROP COLUMN while a view depends on it -- drop the
    # view first, recreate afterward (SELECT * then naturally re-expands to
    # the smaller, pre-migration column set).
    op.execute("DROP VIEW IF EXISTS app.current_report_comparisons;")
    op.drop_column('report_comparisons', 'governance_topic_mix_change', schema='app')
    op.drop_column('report_comparisons', 'governance_share_change_label', schema='app')
    op.drop_column('report_comparisons', 'governance_share_change', schema='app')
    op.drop_column('report_comparisons', 'governance_share_later', schema='app')
    op.drop_column('report_comparisons', 'governance_share_earlier', schema='app')
    op.execute(_REPORT_COMPARISONS_VIEW_SQL)
