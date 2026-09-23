"""governance hit counts (Track 7F.7a.1a: factual M3-G decomposition)

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-09-23 00:00:00.000001

Adds four nullable Integer columns to `report_pair_language_features`:
`governance_hits_earlier`, `governance_hits_later`,
`custom_taxonomy_hits_earlier`, `custom_taxonomy_hits_later` (H
earlier/later). These are the raw counts already computed by
`aggregate_side`/`SidePopulation.custom_category_totals` en route to M3-G
(`governance_share(side) = governance_hits(side) / total_custom_taxonomy_
hits(side)`), now persisted so a governance finding's supporting detail can
state the factual count/share decomposition behind M3-G instead of the
undocumented `|M1-G| < 1.0` "changed little" heuristic (7F.6/7F.7a.1a).
All nullable, no backfill -- existing rows simply have these as NULL until
the next language-signal rebuild (`SIGNAL_VERSION` was bumped alongside this
migration so that rebuild happens automatically, not skipped as "already
current"). `governance_share_earlier/_later/_change` and
`governance_topic_mix_change` (added by `b7c8d9e0f1a2`) are untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c8d9e0f1a2b3'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('report_pair_language_features', sa.Column('governance_hits_earlier', sa.Integer(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('governance_hits_later', sa.Integer(), nullable=True))
    op.add_column(
        'report_pair_language_features', sa.Column('custom_taxonomy_hits_earlier', sa.Integer(), nullable=True)
    )
    op.add_column(
        'report_pair_language_features', sa.Column('custom_taxonomy_hits_later', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('report_pair_language_features', 'custom_taxonomy_hits_later')
    op.drop_column('report_pair_language_features', 'custom_taxonomy_hits_earlier')
    op.drop_column('report_pair_language_features', 'governance_hits_later')
    op.drop_column('report_pair_language_features', 'governance_hits_earlier')
