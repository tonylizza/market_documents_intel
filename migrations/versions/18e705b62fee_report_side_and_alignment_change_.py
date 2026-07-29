"""report-side and alignment-change quality split (Milestone 6 recalibration)

Revision ID: 18e705b62fee
Revises: 21524e40a375
Create Date: 2026-07-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '18e705b62fee'
down_revision: Union[str, Sequence[str], None] = '21524e40a375'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Reuses the 'language_signal_quality' enum type created by 21524e40a375 --
# create_type=False everywhere below so this migration never re-creates it.
_QUALITY_ENUM = postgresql.ENUM(
    'GOOD', 'USABLE', 'NEEDS_REVIEW', 'FAILED', name='language_signal_quality', create_type=False
)


def upgrade() -> None:
    """Upgrade schema."""
    # --- Nullable, no backfill needed (new descriptive/threshold fields) ---
    op.add_column('report_pair_language_features', sa.Column('dictionary_match_rate_earlier', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('dictionary_match_rate_later', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('collision_flagged_word_share', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('unmatched_word_share', sa.Float(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('report_side_warning_reasons', sa.Text(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('report_side_exclusion_reasons', sa.Text(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('alignment_change_warning_reasons', sa.Text(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('alignment_change_exclusion_reasons', sa.Text(), nullable=True))

    # --- NOT NULL float bookkeeping fields: add with a server default of 0,
    # then drop the server default once existing rows are covered (pre-
    # recalibration rows never computed these five populations; 0 correctly
    # signals "not computed under this policy", never a fabricated nonzero
    # count) ---
    for column_name in (
        'alignment_change_analyzed_words_all',
        'alignment_change_analyzed_words_excl_ambiguous',
        'alignment_change_analyzed_words_hml',
        'alignment_change_analyzed_words_hm',
        'alignment_change_analyzed_words_h',
        'ambiguous_words_in_report_side',
    ):
        op.add_column(
            'report_pair_language_features',
            sa.Column(column_name, sa.Float(), nullable=False, server_default='0'),
        )
        op.alter_column('report_pair_language_features', column_name, server_default=None)

    # --- NOT NULL quality/eligibility fields: add nullable, backfill from
    # the deprecated composite (the best available projection for rows that
    # predate this split -- both layers equal what the single blended gate
    # already said), then enforce NOT NULL ---
    op.add_column('report_pair_language_features', sa.Column('report_side_signal_quality', _QUALITY_ENUM, nullable=True))
    op.add_column('report_pair_language_features', sa.Column('report_side_primary_eligible', sa.Boolean(), nullable=True))
    op.add_column('report_pair_language_features', sa.Column('alignment_change_signal_quality', _QUALITY_ENUM, nullable=True))
    op.add_column(
        'report_pair_language_features', sa.Column('alignment_change_primary_eligible', sa.Boolean(), nullable=True)
    )

    op.execute(
        """
        UPDATE report_pair_language_features
        SET report_side_signal_quality = language_signal_quality,
            report_side_primary_eligible = primary_eligible,
            alignment_change_signal_quality = language_signal_quality,
            alignment_change_primary_eligible = primary_eligible
        WHERE report_side_signal_quality IS NULL
        """
    )

    op.alter_column('report_pair_language_features', 'report_side_signal_quality', nullable=False)
    op.alter_column('report_pair_language_features', 'report_side_primary_eligible', nullable=False)
    op.alter_column('report_pair_language_features', 'alignment_change_signal_quality', nullable=False)
    op.alter_column('report_pair_language_features', 'alignment_change_primary_eligible', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('report_pair_language_features', 'alignment_change_primary_eligible')
    op.drop_column('report_pair_language_features', 'alignment_change_signal_quality')
    op.drop_column('report_pair_language_features', 'report_side_primary_eligible')
    op.drop_column('report_pair_language_features', 'report_side_signal_quality')
    op.drop_column('report_pair_language_features', 'ambiguous_words_in_report_side')
    op.drop_column('report_pair_language_features', 'alignment_change_analyzed_words_h')
    op.drop_column('report_pair_language_features', 'alignment_change_analyzed_words_hm')
    op.drop_column('report_pair_language_features', 'alignment_change_analyzed_words_hml')
    op.drop_column('report_pair_language_features', 'alignment_change_analyzed_words_excl_ambiguous')
    op.drop_column('report_pair_language_features', 'alignment_change_analyzed_words_all')
    op.drop_column('report_pair_language_features', 'alignment_change_exclusion_reasons')
    op.drop_column('report_pair_language_features', 'alignment_change_warning_reasons')
    op.drop_column('report_pair_language_features', 'report_side_exclusion_reasons')
    op.drop_column('report_pair_language_features', 'report_side_warning_reasons')
    op.drop_column('report_pair_language_features', 'unmatched_word_share')
    op.drop_column('report_pair_language_features', 'collision_flagged_word_share')
    op.drop_column('report_pair_language_features', 'dictionary_match_rate_later')
    op.drop_column('report_pair_language_features', 'dictionary_match_rate_earlier')
    # 'language_signal_quality' enum type is reused (not owned by this
    # revision) -- never dropped here.
