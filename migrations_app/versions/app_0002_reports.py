"""app reports

Revision ID: app_0002
Revises: app_0001
Create Date: 2026-07-27 14:49:14.509244

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'app_0002'
down_revision: Union[str, Sequence[str], None] = 'app_0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('reports',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('source_report_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=512), nullable=False),
    sa.Column('filename', sa.String(length=512), nullable=False),
    sa.Column('directory_year', sa.Integer(), nullable=False),
    sa.Column('period_start', sa.Date(), nullable=True),
    sa.Column('period_end', sa.Date(), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('narrative_word_count', sa.Integer(), nullable=True),
    sa.Column('extraction_quality', sa.String(length=32), nullable=True),
    sa.Column('extraction_quality_label', sa.String(length=64), nullable=True),
    sa.Column('extraction_warning', sa.Text(), nullable=True),
    sa.Column('chronological_index', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['app.companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'source_report_id', name='uq_app_reports_pub_source'),
    schema='app'
    )
    op.create_index('ix_app_reports_company_id', 'reports', ['company_id'], unique=False, schema='app')
    op.create_index('ix_app_reports_publication_id', 'reports', ['publication_id'], unique=False, schema='app')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_app_reports_publication_id', table_name='reports', schema='app')
    op.drop_index('ix_app_reports_company_id', table_name='reports', schema='app')
    op.drop_table('reports', schema='app')
