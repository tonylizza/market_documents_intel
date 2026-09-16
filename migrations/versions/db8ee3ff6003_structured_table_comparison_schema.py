"""structured table comparison schema

Track 7C.4 (docs/7c4-structured-table-comparison.md): reconstructs the two
validated ACT structured table families (ned_remuneration_policy_table,
total_remuneration_outcomes) from CanonicalBlock into first-class row/
column/cell/footnote structures, and aligns them across adjacent-year
ReportPairs into explicit structured value-change events. Deliberately
does not depend on schedule localization (REMUNERATION is not configured
in 7C.1) -- each table family's own heading pattern locates it directly
within the report's whole canonical document. No existing table is
modified.

Revision ID: db8ee3ff6003
Revises: 3ac7dda97887
Create Date: 2026-09-16 13:25:50.154467

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'db8ee3ff6003'
down_revision: Union[str, Sequence[str], None] = '3ac7dda97887'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'structured_table_extraction_runs',
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('canonical_run_id', sa.UUID(), nullable=False),
        sa.Column('table_family_key', sa.String(length=128), nullable=False),
        sa.Column('algorithm_version', sa.String(length=64), nullable=False),
        sa.Column('configuration_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED',
                    name='structured_table_extraction_run_status'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['canonical_run_id'], ['canonical_extraction_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_structured_table_extraction_runs_report_completed_at',
        'structured_table_extraction_runs', ['report_id', 'completed_at'], unique=False,
    )
    op.create_index(
        'ix_structured_table_extraction_runs_report_family_status',
        'structured_table_extraction_runs', ['report_id', 'table_family_key', 'status'], unique=False,
    )

    op.create_table(
        'structured_table_alignment_runs',
        sa.Column('report_pair_id', sa.UUID(), nullable=False),
        sa.Column('table_family_key', sa.String(length=128), nullable=False),
        sa.Column('earlier_structured_table_extraction_run_id', sa.UUID(), nullable=False),
        sa.Column('later_structured_table_extraction_run_id', sa.UUID(), nullable=False),
        sa.Column('algorithm_version', sa.String(length=64), nullable=False),
        sa.Column('configuration_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED',
                    name='structured_table_alignment_run_status'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('review_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['earlier_structured_table_extraction_run_id'], ['structured_table_extraction_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['later_structured_table_extraction_run_id'], ['structured_table_extraction_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['report_pair_id'], ['report_pairs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_structured_table_alignment_runs_pair_completed_at',
        'structured_table_alignment_runs', ['report_pair_id', 'completed_at'], unique=False,
    )
    op.create_index(
        'ix_structured_table_alignment_runs_pair_family_status',
        'structured_table_alignment_runs', ['report_pair_id', 'table_family_key', 'status'], unique=False,
    )

    op.create_table(
        'structured_tables',
        sa.Column('structured_table_extraction_run_id', sa.UUID(), nullable=False),
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('table_family_key', sa.String(length=128), nullable=False),
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
        sa.Column('source_heading', sa.Text(), nullable=False),
        sa.Column('start_page', sa.Integer(), nullable=False),
        sa.Column('end_page', sa.Integer(), nullable=False),
        sa.Column('table_shape', sa.Enum('RECTANGULAR_MATRIX', name='structured_table_shape'), nullable=False),
        sa.Column('row_identity_type', sa.Enum('ROLE', 'PERSON', name='structured_row_identity_type'), nullable=False),
        sa.Column(
            'analytical_mode',
            postgresql.ENUM(
                'LEXICAL_ONLY', 'LEXICAL_WITH_NUMERIC_CONTEXT', 'STRUCTURED_COMPARISON_PREFERRED',
                'PRESENCE_STATUS_ONLY', 'NOT_ELIGIBLE',
                name='analytical_mode', create_type=False,
            ),
            nullable=False,
        ),
        sa.Column('unit_of_measure', sa.String(length=64), nullable=True),
        sa.Column(
            'reconstruction_status',
            sa.Enum('CLEAN', 'MINOR_CORRECTION_NEEDED', 'MAJOR_LAYOUT_RECONSTRUCTION_NEEDED', 'MULTIMODAL_REQUIRED',
                    name='structured_table_reconstruction_status'),
            nullable=False,
        ),
        sa.Column(
            'reconstruction_confidence',
            postgresql.ENUM('HIGH', 'MEDIUM', 'LOW', 'NEEDS_REVIEW', name='alignment_confidence', create_type=False),
            nullable=False,
        ),
        sa.Column('extraction_note', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['structured_table_extraction_run_id'], ['structured_table_extraction_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('structured_table_extraction_run_id', 'table_family_key', name='uq_structured_tables_run_family'),
    )
    op.create_index('ix_structured_tables_report_family', 'structured_tables', ['report_id', 'table_family_key'], unique=False)

    op.create_table(
        'structured_table_columns',
        sa.Column('structured_table_id', sa.UUID(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('source_label', sa.Text(), nullable=True),
        sa.Column('normalized_key', sa.String(length=128), nullable=False),
        sa.Column('group_label', sa.String(length=128), nullable=True),
        sa.Column('year_ref', sa.Integer(), nullable=True),
        sa.Column('unit_or_currency', sa.String(length=32), nullable=True),
        sa.Column('is_restated', sa.Boolean(), nullable=False),
        sa.Column('source_block_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['source_block_id'], ['canonical_blocks.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['structured_table_id'], ['structured_tables.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('structured_table_id', 'position', name='uq_structured_table_columns_table_position'),
    )

    op.create_table(
        'structured_table_rows',
        sa.Column('structured_table_id', sa.UUID(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('source_label', sa.Text(), nullable=False),
        sa.Column('normalized_identity', sa.String(length=256), nullable=False),
        sa.Column('category_label', sa.Text(), nullable=True),
        sa.Column('row_marker', sa.String(length=8), nullable=True),
        sa.Column('source_block_id', sa.UUID(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['source_block_id'], ['canonical_blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['structured_table_id'], ['structured_tables.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('structured_table_id', 'position', name='uq_structured_table_rows_table_position'),
    )

    op.create_table(
        'structured_table_cells',
        sa.Column('structured_table_row_id', sa.UUID(), nullable=False),
        sa.Column('structured_table_column_id', sa.UUID(), nullable=False),
        sa.Column('raw_value', sa.Text(), nullable=True),
        sa.Column('parsed_numeric_value', sa.Float(), nullable=True),
        sa.Column(
            'cell_status',
            sa.Enum('NUMERIC', 'NIL_DASH', 'ZERO', 'MISSING', 'NOT_APPLICABLE', 'TEXT_VALUE',
                    'COMPARATIVE_ONLY', 'PARTIAL_YEAR_VALUE', name='structured_cell_status'),
            nullable=False,
        ),
        sa.Column('currency_or_unit', sa.String(length=32), nullable=True),
        sa.Column('footnote_marker', sa.String(length=8), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['structured_table_column_id'], ['structured_table_columns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['structured_table_row_id'], ['structured_table_rows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('structured_table_row_id', 'structured_table_column_id', name='uq_structured_table_cells_row_column'),
    )

    op.create_table(
        'structured_table_footnotes',
        sa.Column('structured_table_id', sa.UUID(), nullable=False),
        sa.Column('marker', sa.String(length=8), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('page', sa.Integer(), nullable=False),
        sa.Column('source_block_id', sa.UUID(), nullable=False),
        sa.Column('row_id', sa.UUID(), nullable=True),
        sa.Column('column_id', sa.UUID(), nullable=True),
        sa.Column('cell_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['cell_id'], ['structured_table_cells.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['column_id'], ['structured_table_columns.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['row_id'], ['structured_table_rows.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_block_id'], ['canonical_blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['structured_table_id'], ['structured_tables.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'structured_row_alignments',
        sa.Column('alignment_run_id', sa.UUID(), nullable=False),
        sa.Column('earlier_structured_table_row_id', sa.UUID(), nullable=True),
        sa.Column('later_structured_table_row_id', sa.UUID(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('MATCHED', 'ADDED', 'REMOVED', 'COMPARATIVE_ONLY', 'PARTIAL_YEAR', name='structured_row_alignment_status'),
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
        sa.ForeignKeyConstraint(['alignment_run_id'], ['structured_table_alignment_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['earlier_structured_table_row_id'], ['structured_table_rows.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['later_structured_table_row_id'], ['structured_table_rows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_structured_row_alignments_run', 'structured_row_alignments', ['alignment_run_id'], unique=False)

    op.create_table(
        'structured_column_alignments',
        sa.Column('alignment_run_id', sa.UUID(), nullable=False),
        sa.Column('earlier_structured_table_column_id', sa.UUID(), nullable=True),
        sa.Column('later_structured_table_column_id', sa.UUID(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('MATCHED', 'RENAMED', 'ADDED', 'REMOVED', 'MERGED', name='structured_column_alignment_status'),
            nullable=False,
        ),
        sa.Column(
            'comparability_status',
            sa.Enum('DIRECTLY_COMPARABLE', 'COMPARABLE_WITH_CAVEAT', 'PARTIALLY_COMPARABLE_SCHEMA_CHANGED',
                    'NOT_COMPARABLE', name='structured_comparability_status'),
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
        sa.ForeignKeyConstraint(['alignment_run_id'], ['structured_table_alignment_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['earlier_structured_table_column_id'], ['structured_table_columns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['later_structured_table_column_id'], ['structured_table_columns.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_structured_column_alignments_run', 'structured_column_alignments', ['alignment_run_id'], unique=False)

    op.create_table(
        'structured_value_change_events',
        sa.Column('alignment_run_id', sa.UUID(), nullable=False),
        sa.Column('row_alignment_id', sa.UUID(), nullable=False),
        sa.Column('column_alignment_id', sa.UUID(), nullable=False),
        sa.Column('earlier_structured_table_cell_id', sa.UUID(), nullable=True),
        sa.Column('later_structured_table_cell_id', sa.UUID(), nullable=True),
        sa.Column(
            'event_type',
            sa.Enum('VALUE_UNCHANGED', 'VALUE_INCREASED', 'VALUE_DECREASED', 'ZERO_TO_VALUE', 'VALUE_TO_ZERO',
                    'NIL_TO_VALUE', 'VALUE_TO_NIL', 'MISSING_TO_VALUE', 'VALUE_TO_MISSING', 'COMPARATIVE_ONLY',
                    'PARTIAL_YEAR', 'SCHEMA_CHANGED', 'VALUE_NOT_COMPARABLE', name='structured_value_change_event_type'),
            nullable=False,
        ),
        sa.Column('earlier_raw_value', sa.Text(), nullable=True),
        sa.Column('later_raw_value', sa.Text(), nullable=True),
        sa.Column('earlier_numeric', sa.Float(), nullable=True),
        sa.Column('later_numeric', sa.Float(), nullable=True),
        sa.Column('absolute_change', sa.Float(), nullable=True),
        sa.Column('pct_change', sa.Float(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['alignment_run_id'], ['structured_table_alignment_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['column_alignment_id'], ['structured_column_alignments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['earlier_structured_table_cell_id'], ['structured_table_cells.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['later_structured_table_cell_id'], ['structured_table_cells.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['row_alignment_id'], ['structured_row_alignments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_structured_value_change_events_run', 'structured_value_change_events', ['alignment_run_id'], unique=False)
    op.create_index('ix_structured_value_change_events_row_alignment', 'structured_value_change_events', ['row_alignment_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_structured_value_change_events_row_alignment', table_name='structured_value_change_events')
    op.drop_index('ix_structured_value_change_events_run', table_name='structured_value_change_events')
    op.drop_table('structured_value_change_events')

    op.drop_index('ix_structured_column_alignments_run', table_name='structured_column_alignments')
    op.drop_table('structured_column_alignments')

    op.drop_index('ix_structured_row_alignments_run', table_name='structured_row_alignments')
    op.drop_table('structured_row_alignments')

    op.drop_table('structured_table_footnotes')
    op.drop_table('structured_table_cells')
    op.drop_table('structured_table_rows')
    op.drop_table('structured_table_columns')

    op.drop_index('ix_structured_tables_report_family', table_name='structured_tables')
    op.drop_table('structured_tables')

    op.drop_index('ix_structured_table_alignment_runs_pair_family_status', table_name='structured_table_alignment_runs')
    op.drop_index('ix_structured_table_alignment_runs_pair_completed_at', table_name='structured_table_alignment_runs')
    op.drop_table('structured_table_alignment_runs')

    op.drop_index('ix_structured_table_extraction_runs_report_family_status', table_name='structured_table_extraction_runs')
    op.drop_index('ix_structured_table_extraction_runs_report_completed_at', table_name='structured_table_extraction_runs')
    op.drop_table('structured_table_extraction_runs')

    sa.Enum(name='structured_value_change_event_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_comparability_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_column_alignment_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_row_alignment_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_cell_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_table_reconstruction_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_row_identity_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_table_shape').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_table_alignment_run_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='structured_table_extraction_run_status').drop(op.get_bind(), checkfirst=True)
