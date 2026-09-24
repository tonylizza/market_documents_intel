"""unified Discover topic-change metrics (Track 7F.9)

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-09-24 00:00:00.000000

Adds 22 nullable columns to `report_pair_language_features` for the frozen
7F.8/7F.8a Discover methodology: the C_min topic-change metric
(`{financial_condition,governance,uncertainty}_topic_change`), its count leg
(`*_count_change_per_1000`), its inputs (`feature_eligible_primary_words_*`,
`financial_condition_hits_*`), and supporting-only alignment-unit
diagnostics (`*_supporting_hits`, `*_opposing_hits`,
`*_change_consistency_ratio`, `*_largest_passage_share`).

Governance and uncertainty hit inputs already exist (`governance_hits_*`,
c8d9e0f1a2b3; `uncertainty_count_*`, Milestone 6) and are reused rather
than duplicated. All existing M1/M3/M6 columns are retained. No backfill --
existing rows keep NULLs; `SIGNAL_VERSION` 1.4.0 forces a fresh
`LanguageSignalRun` per pair so new runs populate them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'c8d9e0f1a2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = 'report_pair_language_features'
_CATEGORIES = ('financial_condition', 'governance', 'uncertainty')

_COLUMNS: list[tuple[str, type]] = [
    ('feature_eligible_primary_words_earlier', sa.Integer),
    ('feature_eligible_primary_words_later', sa.Integer),
    ('financial_condition_hits_earlier', sa.Integer),
    ('financial_condition_hits_later', sa.Integer),
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
]


def upgrade() -> None:
    """Upgrade schema."""
    for name, type_ in _COLUMNS:
        op.add_column(_TABLE, sa.Column(name, type_(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for name, _type in reversed(_COLUMNS):
        op.drop_column(_TABLE, name)
