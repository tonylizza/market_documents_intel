"""governance share/topic-mix metrics (Track 7F.7a.1: M3-G/M6-G)

Revision ID: b7c8d9e0f1a2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-23 00:00:00.000000

Adds four nullable Float columns to `report_pair_language_features` for the
7F.7a ADOPT_GOVERNANCE_SHARE_WITH_THRESHOLD methodology: M3-G
(governance_share_earlier/_later/_change) and M6-G
(governance_topic_mix_change). All nullable, no backfill -- existing rows
simply have these as NULL until the next language-signal rebuild
(`SIGNAL_VERSION` was bumped alongside this migration so that rebuild
happens automatically, not skipped as "already current"). Exact mirror of
the `f1a2b3c4d5e6` financial-condition M3/M6b migration, applied to
governance. `governance_language_change` (M1-G) and `governance_rate_
earlier/_later` are untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('report_pair_language_features', sa.Column('governance_share_earlier', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('governance_share_later', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('governance_share_change', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('governance_topic_mix_change', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('report_pair_language_features', 'governance_topic_mix_change')
    op.drop_column('report_pair_language_features', 'governance_share_change')
    op.drop_column('report_pair_language_features', 'governance_share_later')
    op.drop_column('report_pair_language_features', 'governance_share_earlier')
