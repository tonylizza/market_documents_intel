"""canonical pdf source schema

Track 7C.1a (docs/7c1a-canonical-source-representation.md): a
source-faithful, block/line/span-granular PDF representation built
directly from PyMuPDF, persisted alongside (never in place of) the legacy
Page/TextBlock schema from Milestone 2. No existing table is modified.

Revision ID: a1f6c9e2d4b7
Revises: 5c74ac77a25e
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1f6c9e2d4b7'
down_revision: Union[str, Sequence[str], None] = '5c74ac77a25e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'canonical_extraction_runs',
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('extractor_name', sa.String(length=64), nullable=False),
        sa.Column('extractor_version', sa.String(length=64), nullable=False),
        sa.Column('configuration_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED',
                    name='canonical_extraction_status'),
            nullable=False,
        ),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('expected_page_count', sa.Integer(), nullable=True),
        sa.Column('processed_page_count', sa.Integer(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_canonical_extraction_runs_report_status',
        'canonical_extraction_runs', ['report_id', 'status'], unique=False,
    )
    op.create_index(
        'ix_canonical_extraction_runs_report_completed_at',
        'canonical_extraction_runs', ['report_id', 'completed_at'], unique=False,
    )

    op.create_table(
        'canonical_pages',
        sa.Column('canonical_run_id', sa.UUID(), nullable=False),
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('width', sa.Float(), nullable=False),
        sa.Column('height', sa.Float(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['canonical_run_id'], ['canonical_extraction_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('canonical_run_id', 'page_number', name='uq_canonical_pages_run_page_number'),
    )
    op.create_index(
        'ix_canonical_pages_report_page_number', 'canonical_pages', ['report_id', 'page_number'], unique=False
    )

    op.create_table(
        'canonical_blocks',
        sa.Column('page_id', sa.UUID(), nullable=False),
        sa.Column('block_order', sa.Integer(), nullable=False),
        sa.Column('native_type', sa.Integer(), nullable=False),
        sa.Column('x0', sa.Float(), nullable=False),
        sa.Column('y0', sa.Float(), nullable=False),
        sa.Column('x1', sa.Float(), nullable=False),
        sa.Column('y1', sa.Float(), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['canonical_pages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('page_id', 'block_order', name='uq_canonical_blocks_page_block_order'),
    )
    op.create_index(
        'ix_canonical_blocks_page_block_order', 'canonical_blocks', ['page_id', 'block_order'], unique=False
    )

    op.create_table(
        'canonical_lines',
        sa.Column('block_id', sa.UUID(), nullable=False),
        sa.Column('line_order', sa.Integer(), nullable=False),
        sa.Column('x0', sa.Float(), nullable=False),
        sa.Column('y0', sa.Float(), nullable=False),
        sa.Column('x1', sa.Float(), nullable=False),
        sa.Column('y1', sa.Float(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['canonical_blocks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('block_id', 'line_order', name='uq_canonical_lines_block_line_order'),
    )
    op.create_index(
        'ix_canonical_lines_block_line_order', 'canonical_lines', ['block_id', 'line_order'], unique=False
    )

    op.create_table(
        'canonical_spans',
        sa.Column('line_id', sa.UUID(), nullable=False),
        sa.Column('span_order', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('x0', sa.Float(), nullable=False),
        sa.Column('y0', sa.Float(), nullable=False),
        sa.Column('x1', sa.Float(), nullable=False),
        sa.Column('y1', sa.Float(), nullable=False),
        sa.Column('font_name', sa.String(length=128), nullable=True),
        sa.Column('font_size', sa.Float(), nullable=True),
        sa.Column('font_flags', sa.Integer(), nullable=True),
        sa.Column('is_bold', sa.Boolean(), nullable=True),
        sa.Column('color', sa.Integer(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['line_id'], ['canonical_lines.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('line_id', 'span_order', name='uq_canonical_spans_line_span_order'),
    )
    op.create_index(
        'ix_canonical_spans_line_span_order', 'canonical_spans', ['line_id', 'span_order'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_canonical_spans_line_span_order', table_name='canonical_spans')
    op.drop_table('canonical_spans')

    op.drop_index('ix_canonical_lines_block_line_order', table_name='canonical_lines')
    op.drop_table('canonical_lines')

    op.drop_index('ix_canonical_blocks_page_block_order', table_name='canonical_blocks')
    op.drop_table('canonical_blocks')

    op.drop_index('ix_canonical_pages_report_page_number', table_name='canonical_pages')
    op.drop_table('canonical_pages')

    op.drop_index('ix_canonical_extraction_runs_report_completed_at', table_name='canonical_extraction_runs')
    op.drop_index('ix_canonical_extraction_runs_report_status', table_name='canonical_extraction_runs')
    op.drop_table('canonical_extraction_runs')

    sa.Enum(name='canonical_extraction_status').drop(op.get_bind(), checkfirst=True)
