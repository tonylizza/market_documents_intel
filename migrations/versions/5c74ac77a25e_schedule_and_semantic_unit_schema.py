"""schedule and semantic unit schema

Track 7C.1 (docs/7c1-schedule-localization-plan.md): schedule localization
and headed-narrative semantic-unit extraction, built as a parallel
replacement track alongside the existing passage pipeline. No existing
table is modified.

Revision ID: 5c74ac77a25e
Revises: ce5dc703671d
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5c74ac77a25e'
down_revision: Union[str, Sequence[str], None] = 'ce5dc703671d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'schedule_localization_runs',
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('extraction_run_id', sa.UUID(), nullable=False),
        sa.Column(
            'schedule',
            sa.Enum(
                'CEO_REVIEW', 'CHAIR_REVIEW', 'FINANCIAL_PERFORMANCE', 'MATERIAL_RISKS',
                'STRATEGY', 'OUTLOOK', 'CORPORATE_GOVERNANCE', 'REMUNERATION',
                'LEGAL_REGULATORY', 'MATERIAL_MATTERS_OPERATING_ENVIRONMENT',
                name='normalized_schedule',
            ),
            nullable=False,
        ),
        sa.Column('algorithm_version', sa.String(length=64), nullable=False),
        sa.Column('configuration_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED',
                    name='schedule_localization_run_status'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['extraction_run_id'], ['extraction_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_schedule_localization_runs_report_schedule_status',
        'schedule_localization_runs', ['report_id', 'schedule', 'status'], unique=False,
    )
    op.create_index(
        'ix_schedule_localization_runs_report_completed_at',
        'schedule_localization_runs', ['report_id', 'completed_at'], unique=False,
    )

    op.create_table(
        'schedule_instances',
        sa.Column('schedule_localization_run_id', sa.UUID(), nullable=False),
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column(
            'schedule',
            sa.Enum(name='normalized_schedule', create_type=False),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'FOUND_PRIMARY_ONLY', 'FOUND_PRIMARY_AND_SUPPORTING', 'DISTRIBUTED_NO_CLEAR_PRIMARY',
                'NOT_FOUND', 'NOT_APPLICABLE', name='schedule_localization_status',
            ),
            nullable=False,
        ),
        sa.Column('heading_text', sa.String(length=512), nullable=True),
        sa.Column('start_page', sa.Integer(), nullable=True),
        sa.Column('end_page', sa.Integer(), nullable=True),
        sa.Column(
            'boundary_confidence',
            sa.Enum('HIGH', 'MEDIUM', 'LOW', name='boundary_confidence'),
            nullable=True,
        ),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('reasoning_summary', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ['schedule_localization_run_id'], ['schedule_localization_runs.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'schedule_localization_run_id', 'schedule', name='uq_schedule_instances_run_schedule'
        ),
    )
    op.create_index(
        'ix_schedule_instances_report_schedule', 'schedule_instances', ['report_id', 'schedule'], unique=False
    )

    op.create_table(
        'schedule_instance_supporting_spans',
        sa.Column('schedule_instance_id', sa.UUID(), nullable=False),
        sa.Column('heading_text', sa.String(length=512), nullable=True),
        sa.Column('start_page', sa.Integer(), nullable=False),
        sa.Column('end_page', sa.Integer(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['schedule_instance_id'], ['schedule_instances.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_schedule_instance_supporting_spans_instance_id',
        'schedule_instance_supporting_spans', ['schedule_instance_id'], unique=False,
    )

    op.create_table(
        'semantic_unit_runs',
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('schedule_localization_run_id', sa.UUID(), nullable=False),
        sa.Column(
            'schedule',
            sa.Enum(name='normalized_schedule', create_type=False),
            nullable=False,
        ),
        sa.Column('algorithm_version', sa.String(length=64), nullable=False),
        sa.Column('configuration_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED',
                    name='semantic_unit_run_status'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['schedule_localization_run_id'], ['schedule_localization_runs.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_semantic_unit_runs_report_schedule_status',
        'semantic_unit_runs', ['report_id', 'schedule', 'status'], unique=False,
    )
    op.create_index(
        'ix_semantic_unit_runs_report_completed_at',
        'semantic_unit_runs', ['report_id', 'completed_at'], unique=False,
    )

    op.create_table(
        'semantic_units',
        sa.Column('semantic_unit_run_id', sa.UUID(), nullable=False),
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('schedule_instance_id', sa.UUID(), nullable=False),
        sa.Column('unit_key', sa.String(length=128), nullable=False),
        sa.Column('unit_type', sa.Enum('HEADED_NARRATIVE_UNIT', name='semantic_unit_type'), nullable=False),
        sa.Column('source_heading', sa.String(length=512), nullable=False),
        sa.Column('start_page', sa.Integer(), nullable=False),
        sa.Column(
            'boundary_strategy',
            sa.Enum('NEXT_HEADING', 'ANCHOR_SENTENCE', name='semantic_unit_boundary_strategy'),
            nullable=False,
        ),
        sa.Column('boundary_anchor_text', sa.Text(), nullable=True),
        sa.Column(
            'boundary_status',
            sa.Enum('RESOLVED', 'UNRESOLVED', name='semantic_unit_boundary_status'),
            nullable=False,
        ),
        sa.Column(
            'boundary_confidence',
            sa.Enum(name='boundary_confidence', create_type=False),
            nullable=True,
        ),
        sa.Column('end_page', sa.Integer(), nullable=True),
        sa.Column('source_text', sa.Text(), nullable=True),
        sa.Column('word_count', sa.Integer(), nullable=True),
        sa.Column('extraction_note', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['semantic_unit_run_id'], ['semantic_unit_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['schedule_instance_id'], ['schedule_instances.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'semantic_unit_run_id', 'schedule_instance_id', 'unit_key',
            name='uq_semantic_units_run_instance_unit_key',
        ),
    )
    op.create_index(
        'ix_semantic_units_report_unit_key', 'semantic_units', ['report_id', 'unit_key'], unique=False
    )
    op.create_index(
        'ix_semantic_units_report_boundary_status',
        'semantic_units', ['report_id', 'boundary_status'], unique=False,
    )

    op.create_table(
        'semantic_unit_source_blocks',
        sa.Column('semantic_unit_id', sa.UUID(), nullable=False),
        sa.Column('text_block_id', sa.UUID(), nullable=False),
        sa.Column('block_order', sa.Integer(), nullable=False),
        sa.Column('char_start', sa.Integer(), nullable=False),
        sa.Column('char_end', sa.Integer(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['semantic_unit_id'], ['semantic_units.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['text_block_id'], ['text_blocks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'semantic_unit_id', 'block_order', name='uq_semantic_unit_source_blocks_unit_order'
        ),
    )
    op.create_index(
        'ix_semantic_unit_source_blocks_unit_id', 'semantic_unit_source_blocks', ['semantic_unit_id'], unique=False
    )
    op.create_index(
        'ix_semantic_unit_source_blocks_text_block_id',
        'semantic_unit_source_blocks', ['text_block_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_semantic_unit_source_blocks_text_block_id', table_name='semantic_unit_source_blocks')
    op.drop_index('ix_semantic_unit_source_blocks_unit_id', table_name='semantic_unit_source_blocks')
    op.drop_table('semantic_unit_source_blocks')

    op.drop_index('ix_semantic_units_report_boundary_status', table_name='semantic_units')
    op.drop_index('ix_semantic_units_report_unit_key', table_name='semantic_units')
    op.drop_table('semantic_units')

    op.drop_index('ix_semantic_unit_runs_report_completed_at', table_name='semantic_unit_runs')
    op.drop_index('ix_semantic_unit_runs_report_schedule_status', table_name='semantic_unit_runs')
    op.drop_table('semantic_unit_runs')

    op.drop_index('ix_schedule_instance_supporting_spans_instance_id', table_name='schedule_instance_supporting_spans')
    op.drop_table('schedule_instance_supporting_spans')

    op.drop_index('ix_schedule_instances_report_schedule', table_name='schedule_instances')
    op.drop_table('schedule_instances')

    op.drop_index('ix_schedule_localization_runs_report_completed_at', table_name='schedule_localization_runs')
    op.drop_index('ix_schedule_localization_runs_report_schedule_status', table_name='schedule_localization_runs')
    op.drop_table('schedule_localization_runs')

    sa.Enum(name='semantic_unit_boundary_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='semantic_unit_boundary_strategy').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='semantic_unit_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='semantic_unit_run_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='boundary_confidence').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='schedule_localization_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='schedule_localization_run_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='normalized_schedule').drop(op.get_bind(), checkfirst=True)
