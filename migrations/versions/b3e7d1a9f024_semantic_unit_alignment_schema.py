"""semantic unit alignment schema

Track 7C.2 (docs/7c2-semantic-unit-alignment.md): cross-year alignment of
persisted SemanticUnit records. No existing table is modified.

Revision ID: b3e7d1a9f024
Revises: a1f6c9e2d4b7
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b3e7d1a9f024'
down_revision: Union[str, Sequence[str], None] = 'a1f6c9e2d4b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'semantic_unit_alignment_runs',
        sa.Column('report_pair_id', sa.UUID(), nullable=False),
        sa.Column('earlier_semantic_unit_run_id', sa.UUID(), nullable=False),
        sa.Column('later_semantic_unit_run_id', sa.UUID(), nullable=False),
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
                    name='semantic_unit_alignment_run_status'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['report_pair_id'], ['report_pairs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['earlier_semantic_unit_run_id'], ['semantic_unit_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['later_semantic_unit_run_id'], ['semantic_unit_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_semantic_unit_alignment_runs_pair_schedule_status',
        'semantic_unit_alignment_runs', ['report_pair_id', 'schedule', 'status'], unique=False,
    )
    op.create_index(
        'ix_semantic_unit_alignment_runs_pair_completed_at',
        'semantic_unit_alignment_runs', ['report_pair_id', 'completed_at'], unique=False,
    )

    op.create_table(
        'semantic_unit_alignments',
        sa.Column('alignment_run_id', sa.UUID(), nullable=False),
        sa.Column('report_pair_id', sa.UUID(), nullable=False),
        sa.Column('earlier_semantic_unit_id', sa.UUID(), nullable=True),
        sa.Column('later_semantic_unit_id', sa.UUID(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'MATCHED', 'RENAMED', 'ADDED', 'REMOVED', 'UNRESOLVED_UPSTREAM', 'AMBIGUOUS',
                name='semantic_unit_alignment_status',
            ),
            nullable=False,
        ),
        sa.Column(
            'confidence',
            postgresql.ENUM('HIGH', 'MEDIUM', 'LOW', 'NEEDS_REVIEW', name='alignment_confidence', create_type=False),
            nullable=False,
        ),
        sa.Column('evidence', sa.Text(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['alignment_run_id'], ['semantic_unit_alignment_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['report_pair_id'], ['report_pairs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['earlier_semantic_unit_id'], ['semantic_units.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['later_semantic_unit_id'], ['semantic_units.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_semantic_unit_alignments_run_id', 'semantic_unit_alignments', ['alignment_run_id'], unique=False
    )
    op.create_index(
        'ix_semantic_unit_alignments_report_pair_id', 'semantic_unit_alignments', ['report_pair_id'], unique=False
    )
    op.create_index(
        'ix_semantic_unit_alignments_status', 'semantic_unit_alignments', ['alignment_run_id', 'status'], unique=False
    )
    op.create_index(
        'uq_semantic_unit_alignments_run_later',
        'semantic_unit_alignments', ['alignment_run_id', 'later_semantic_unit_id'],
        unique=True, postgresql_where=sa.text('later_semantic_unit_id IS NOT NULL'),
    )
    op.create_index(
        'uq_semantic_unit_alignments_run_earlier',
        'semantic_unit_alignments', ['alignment_run_id', 'earlier_semantic_unit_id'],
        unique=True, postgresql_where=sa.text('earlier_semantic_unit_id IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_semantic_unit_alignments_run_earlier', table_name='semantic_unit_alignments')
    op.drop_index('uq_semantic_unit_alignments_run_later', table_name='semantic_unit_alignments')
    op.drop_index('ix_semantic_unit_alignments_status', table_name='semantic_unit_alignments')
    op.drop_index('ix_semantic_unit_alignments_report_pair_id', table_name='semantic_unit_alignments')
    op.drop_index('ix_semantic_unit_alignments_run_id', table_name='semantic_unit_alignments')
    op.drop_table('semantic_unit_alignments')

    op.drop_index('ix_semantic_unit_alignment_runs_pair_completed_at', table_name='semantic_unit_alignment_runs')
    op.drop_index('ix_semantic_unit_alignment_runs_pair_schedule_status', table_name='semantic_unit_alignment_runs')
    op.drop_table('semantic_unit_alignment_runs')

    sa.Enum(name='semantic_unit_alignment_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='semantic_unit_alignment_run_status').drop(op.get_bind(), checkfirst=True)
