"""financial-condition share/topic-mix metrics (Track 7F.4: M3/M6b)

Revision ID: f1a2b3c4d5e6
Revises: a4c1e8f2b6d9
Create Date: 2026-09-22 00:00:00.000000

Adds four nullable Float columns to `report_pair_language_features` for the
7F.3 ADOPT_M3_WITH_THRESHOLD methodology: M3
(financial_condition_share_earlier/_later/_change) and M6b
(financial_condition_topic_mix_change). All nullable, no backfill --
existing rows simply have these as NULL until the next language-signal
rebuild (`SIGNAL_VERSION` was bumped alongside this migration so that
rebuild happens automatically, not skipped as "already current").
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'a4c1e8f2b6d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('report_pair_language_features', sa.Column('financial_condition_share_earlier', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('financial_condition_share_later', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('financial_condition_share_change', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('financial_condition_topic_mix_change', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('report_pair_language_features', 'financial_condition_topic_mix_change')
    op.drop_column('report_pair_language_features', 'financial_condition_share_change')
    op.drop_column('report_pair_language_features', 'financial_condition_share_later')
    op.drop_column('report_pair_language_features', 'financial_condition_share_earlier')
