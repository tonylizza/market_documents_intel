"""governance hit counts (Track 7F.7a.1a: factual M3-G decomposition)

Revision ID: app_0013
Revises: app_0012
Create Date: 2026-09-23 00:00:00.000001

Adds four columns to `app.report_comparisons`: `governance_hits_earlier`,
`governance_hits_later`, `custom_taxonomy_hits_earlier`,
`custom_taxonomy_hits_later` (H earlier/later). These are the raw counts
behind M3-G's share ratio (`governance_share(side) = governance_hits(side) /
custom_taxonomy_hits(side)`), published so the comparison/evidence UI can
state the factual count/share decomposition for a governance finding
instead of the removed `|M1-G| < 1.0` "changed little" heuristic
(7F.6/7F.7a.1a). Mirrors `c8d9e0f1a2b3` on the research side.

`app.current_report_comparisons` is a `SELECT t.*` view -- Postgres expands
`*` to an explicit column list at `CREATE`/`CREATE OR REPLACE` time, so this
migration must explicitly `CREATE OR REPLACE` the view after adding the
columns (upgrade) and before dropping them (downgrade), same pattern as
app_0006/app_0011/app_0012.

IMPORTANT (per the 7F.5/app_0011 precedent): `CREATE OR REPLACE VIEW` on
`current_report_comparisons` can silently drop `app_readonly`'s SELECT
grant on the view. Any rollout that applies this migration MUST immediately
follow it with `scripts/sql/app_grants.sql` (or `market-documents publish
app-init-roles`) -- this is not optional, see
`docs/governance-metric-implementation-7f7a1.md` Production readiness.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from market_documents.publishing.schema import CURRENT_VIEWS

# revision identifiers, used by Alembic.
revision: str = 'app_0013'
down_revision: Union[str, Sequence[str], None] = 'app_0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VIEW_SQL_BY_NAME = dict(CURRENT_VIEWS)
_REPORT_COMPARISONS_VIEW_SQL = _VIEW_SQL_BY_NAME["current_report_comparisons"]


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('report_comparisons', sa.Column('governance_hits_earlier', sa.Integer(), nullable=True), schema='app')
    op.add_column('report_comparisons', sa.Column('governance_hits_later', sa.Integer(), nullable=True), schema='app')
    op.add_column(
        'report_comparisons', sa.Column('custom_taxonomy_hits_earlier', sa.Integer(), nullable=True), schema='app'
    )
    op.add_column(
        'report_comparisons', sa.Column('custom_taxonomy_hits_later', sa.Integer(), nullable=True), schema='app'
    )
    # Re-expand the view's `SELECT *` to include the four new columns.
    op.execute(_REPORT_COMPARISONS_VIEW_SQL)


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres refuses to DROP COLUMN while a view depends on it -- drop the
    # view first, recreate afterward (SELECT * then naturally re-expands to
    # the smaller, pre-migration column set).
    op.execute("DROP VIEW IF EXISTS app.current_report_comparisons;")
    op.drop_column('report_comparisons', 'custom_taxonomy_hits_later', schema='app')
    op.drop_column('report_comparisons', 'custom_taxonomy_hits_earlier', schema='app')
    op.drop_column('report_comparisons', 'governance_hits_later', schema='app')
    op.drop_column('report_comparisons', 'governance_hits_earlier', schema='app')
    op.execute(_REPORT_COMPARISONS_VIEW_SQL)
