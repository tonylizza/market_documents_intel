"""analytical eligibility and lexical comparison schema

Track 7C.3 (docs/7c3-analytical-eligibility-and-lexical-comparison.md):
routes persisted SemanticUnitAlignment rows to an analytical comparison
mode, and persists lexical-change metrics for LEXICAL_ONLY decisions. No
existing table is modified.

Revision ID: 3b24f4904672
Revises: b3e7d1a9f024
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3b24f4904672'
down_revision: Union[str, Sequence[str], None] = 'b3e7d1a9f024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'analytical_decision_runs',
        sa.Column('alignment_run_id', sa.UUID(), nullable=False),
        sa.Column('report_pair_id', sa.UUID(), nullable=False),
        sa.Column(
            'schedule',
            postgresql.ENUM(
                'CEO_REVIEW', 'CHAIR_REVIEW', 'FINANCIAL_PERFORMANCE', 'MATERIAL_RISKS',
                'STRATEGY', 'OUTLOOK', 'CORPORATE_GOVERNANCE', 'REMUNERATION',
                'LEGAL_REGULATORY', 'MATERIAL_MATTERS_OPERATING_ENVIRONMENT',
                name='normalized_schedule', create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('algorithm_version', sa.String(length=64), nullable=False),
        sa.Column('configuration_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED',
                    name='analytical_decision_run_status'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['alignment_run_id'], ['semantic_unit_alignment_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['report_pair_id'], ['report_pairs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_analytical_decision_runs_pair_schedule_status',
        'analytical_decision_runs', ['report_pair_id', 'schedule', 'status'], unique=False,
    )
    op.create_index(
        'ix_analytical_decision_runs_pair_completed_at',
        'analytical_decision_runs', ['report_pair_id', 'completed_at'], unique=False,
    )

    op.create_table(
        'analytical_decisions',
        sa.Column('decision_run_id', sa.UUID(), nullable=False),
        sa.Column('semantic_unit_alignment_id', sa.UUID(), nullable=False),
        sa.Column(
            'analytical_mode',
            sa.Enum(
                'LEXICAL_ONLY', 'LEXICAL_WITH_NUMERIC_CONTEXT', 'STRUCTURED_COMPARISON_PREFERRED',
                'PRESENCE_STATUS_ONLY', 'NOT_ELIGIBLE',
                name='analytical_mode',
            ),
            nullable=False,
        ),
        sa.Column(
            'confidence',
            postgresql.ENUM('HIGH', 'MEDIUM', 'LOW', 'NEEDS_REVIEW', name='alignment_confidence', create_type=False),
            nullable=False,
        ),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['decision_run_id'], ['analytical_decision_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['semantic_unit_alignment_id'], ['semantic_unit_alignments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('decision_run_id', 'semantic_unit_alignment_id', name='uq_analytical_decisions_run_alignment'),
    )
    op.create_index(
        'ix_analytical_decisions_run_id', 'analytical_decisions', ['decision_run_id'], unique=False
    )
    op.create_index(
        'ix_analytical_decisions_alignment_id', 'analytical_decisions', ['semantic_unit_alignment_id'], unique=False
    )
    op.create_index(
        'ix_analytical_decisions_mode', 'analytical_decisions', ['decision_run_id', 'analytical_mode'], unique=False
    )

    op.create_table(
        'lexical_unit_comparisons',
        sa.Column('analytical_decision_id', sa.UUID(), nullable=False),
        sa.Column('semantic_unit_alignment_id', sa.UUID(), nullable=False),
        sa.Column('lexical_cosine_similarity', sa.Float(), nullable=True),
        sa.Column('unigram_jaccard', sa.Float(), nullable=True),
        sa.Column('bigram_jaccard', sa.Float(), nullable=True),
        sa.Column('edit_similarity', sa.Float(), nullable=True),
        sa.Column('sequence_similarity', sa.Float(), nullable=True),
        sa.Column('earlier_word_count', sa.Integer(), nullable=False),
        sa.Column('later_word_count', sa.Integer(), nullable=False),
        sa.Column('word_count_change', sa.Integer(), nullable=False),
        sa.Column('word_count_change_pct', sa.Float(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analytical_decision_id'], ['analytical_decisions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['semantic_unit_alignment_id'], ['semantic_unit_alignments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('analytical_decision_id', name='uq_lexical_unit_comparisons_decision'),
    )
    op.create_index(
        'ix_lexical_unit_comparisons_alignment_id', 'lexical_unit_comparisons', ['semantic_unit_alignment_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_lexical_unit_comparisons_alignment_id', table_name='lexical_unit_comparisons')
    op.drop_table('lexical_unit_comparisons')

    op.drop_index('ix_analytical_decisions_mode', table_name='analytical_decisions')
    op.drop_index('ix_analytical_decisions_alignment_id', table_name='analytical_decisions')
    op.drop_index('ix_analytical_decisions_run_id', table_name='analytical_decisions')
    op.drop_table('analytical_decisions')

    op.drop_index('ix_analytical_decision_runs_pair_completed_at', table_name='analytical_decision_runs')
    op.drop_index('ix_analytical_decision_runs_pair_schedule_status', table_name='analytical_decision_runs')
    op.drop_table('analytical_decision_runs')

    sa.Enum(name='analytical_mode').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='analytical_decision_run_status').drop(op.get_bind(), checkfirst=True)
