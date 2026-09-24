"""unified Discover topic-change metrics (Track 7F.9)

Revision ID: app_0015
Revises: app_0014
Create Date: 2026-09-24 00:00:00.000000

Adds 26 nullable columns to `app.report_comparisons` -- the thin,
per-publication layer only; no `app_artifacts` table changes. Mirrors the
research-side `d9e0f1a2b3c4` columns (C_min topic change, count leg, hit/
word inputs, supporting-only alignment-unit diagnostics) plus
`uncertainty_hits_*` (published from research `uncertainty_count_*`) and
the net-tone components `positive_rate_change`/`negative_rate_change`.

`app.current_report_comparisons` is a `SELECT t.*` view -- Postgres expands
`*` at `CREATE`/`CREATE OR REPLACE` time, so the view is explicitly
re-created after adding the columns (upgrade) and dropped before removing
them (downgrade), same pattern as app_0006/app_0011/app_0012/app_0013.

IMPORTANT (7F.5/app_0011 precedent): any rollout that applies this
migration must follow it with `scripts/sql/app_grants.sql` so
`app_readonly`'s SELECT grant on the view is guaranteed after the downgrade
path's DROP/CREATE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from market_documents.publishing.schema import CURRENT_VIEWS

# revision identifiers, used by Alembic.
revision: str = 'app_0015'
down_revision: Union[str, Sequence[str], None] = 'app_0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VIEW_SQL_BY_NAME = dict(CURRENT_VIEWS)
_REPORT_COMPARISONS_VIEW_SQL = _VIEW_SQL_BY_NAME["current_report_comparisons"]
_CATEGORIES = ('financial_condition', 'governance', 'uncertainty')

_COLUMNS: list[tuple[str, type]] = [
    ('feature_eligible_primary_words_earlier', sa.Integer),
    ('feature_eligible_primary_words_later', sa.Integer),
    ('financial_condition_hits_earlier', sa.Integer),
    ('financial_condition_hits_later', sa.Integer),
    ('uncertainty_hits_earlier', sa.Integer),
    ('uncertainty_hits_later', sa.Integer),
    *[(f'{c}_count_change_per_1000', sa.Float) for c in _CATEGORIES],
    *[(f'{c}_topic_change', sa.Float) for c in _CATEGORIES],
    *[
        column
        for c in _CATEGORIES
        for column in (
            (f'{c}_supporting_hits', sa.Integer),
            (f'{c}_opposing_hits', sa.Integer),
            (f'{c}_change_consistency_ratio', sa.Float),
            (f'{c}_largest_passage_share', sa.Float),
        )
    ],
    ('positive_rate_change', sa.Float),
    ('negative_rate_change', sa.Float),
]


def upgrade() -> None:
    """Upgrade schema."""
    for name, type_ in _COLUMNS:
        op.add_column('report_comparisons', sa.Column(name, type_(), nullable=True), schema='app')
    # Re-expand the view's `SELECT *` to include the new columns.
    op.execute(_REPORT_COMPARISONS_VIEW_SQL)


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres refuses to DROP COLUMN while a view depends on it.
    op.execute("DROP VIEW IF EXISTS app.current_report_comparisons;")
    for name, _type in reversed(_COLUMNS):
        op.drop_column('report_comparisons', name, schema='app')
    op.execute(_REPORT_COMPARISONS_VIEW_SQL)
