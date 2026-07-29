"""app schema bootstrap

Revision ID: app_0001
Revises:
Create Date: 2026-07-27 14:49:14.509244

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from market_documents.publishing.schema import CREATE_SCHEMAS_SQL

# revision identifiers, used by Alembic.
revision: str = 'app_0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Belt-and-suspenders: migrations_app/env.py already creates both
    # schemas before configuring the migration context (Alembic can't create
    # the schema its own app_internal.alembic_version table lives in), but
    # this makes the migration self-contained if ever run through a
    # different env.py.
    for statement in CREATE_SCHEMAS_SQL:
        op.execute(statement)

    op.create_table('publications',
    sa.Column('publication_version', sa.String(length=64), nullable=False),
    sa.Column('source_database_identifier', sa.String(length=255), nullable=False),
    sa.Column('source_schema_version', sa.String(length=64), nullable=False),
    sa.Column('source_configuration_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('company_count', sa.Integer(), nullable=True),
    sa.Column('report_count', sa.Integer(), nullable=True),
    sa.Column('comparison_count', sa.Integer(), nullable=True),
    sa.Column('passage_count', sa.Integer(), nullable=True),
    sa.Column('passage_comparison_count', sa.Integer(), nullable=True),
    sa.Column('language_metric_count', sa.Integer(), nullable=True),
    sa.Column('passage_language_signal_count', sa.Integer(), nullable=True),
    sa.Column('discovery_item_count', sa.Integer(), nullable=True),
    sa.Column('validation_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('PENDING', 'BUILDING', 'VALIDATING', 'READY', 'ACTIVE', 'FAILED', 'SUPERSEDED')", name='ck_publications_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_version', name='uq_publications_version'),
    schema='app_internal'
    )
    op.create_table('companies',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('source_company_id', sa.UUID(), nullable=False),
    sa.Column('ticker', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('short_name', sa.String(length=64), nullable=True),
    sa.Column('sector', sa.String(length=128), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('first_report_period_end', sa.Date(), nullable=True),
    sa.Column('latest_report_period_end', sa.Date(), nullable=True),
    sa.Column('report_count', sa.Integer(), nullable=False),
    sa.Column('comparison_count', sa.Integer(), nullable=False),
    sa.Column('latest_comparison_id', sa.UUID(), nullable=True),
    sa.Column('historical_peak_comparison_id', sa.UUID(), nullable=True),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.Column('has_current_data', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'source_company_id', name='uq_app_companies_pub_source'),
    schema='app'
    )
    op.create_index('ix_app_companies_publication_id', 'companies', ['publication_id'], unique=False, schema='app')
    op.create_table('metric_definitions',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('metric_key', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=128), nullable=False),
    sa.Column('short_description', sa.Text(), nullable=False),
    sa.Column('technical_description', sa.Text(), nullable=False),
    sa.Column('unit', sa.String(length=32), nullable=False),
    sa.Column('direction_interpretation', sa.Text(), nullable=False),
    sa.Column('methodology_anchor', sa.String(length=255), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'metric_key', name='uq_app_metric_definitions_pub_key'),
    schema='app'
    )
    op.create_table('metric_label_thresholds',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('metric_key', sa.String(length=64), nullable=False),
    sa.Column('threshold_version', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=64), nullable=False),
    sa.Column('minimum_value', sa.Float(), nullable=True),
    sa.Column('maximum_value', sa.Float(), nullable=True),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'metric_key', 'threshold_version', 'label', name='uq_app_metric_label_thresholds_scope'),
    schema='app'
    )
    op.create_index('ix_app_metric_label_thresholds_metric_key', 'metric_label_thresholds', ['metric_key'], unique=False, schema='app')
    op.create_table('application_state',
    sa.Column('singleton_key', sa.String(length=16), nullable=False),
    sa.Column('active_publication_id', sa.UUID(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['active_publication_id'], ['app_internal.publications.id'], ),
    sa.PrimaryKeyConstraint('singleton_key'),
    schema='app_internal'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('application_state', schema='app_internal')
    op.drop_index('ix_app_metric_label_thresholds_metric_key', table_name='metric_label_thresholds', schema='app')
    op.drop_table('metric_label_thresholds', schema='app')
    op.drop_table('metric_definitions', schema='app')
    op.drop_index('ix_app_companies_publication_id', table_name='companies', schema='app')
    op.drop_table('companies', schema='app')
    op.drop_table('publications', schema='app_internal')
    # Schemas are intentionally never dropped here: this migration's own
    # `alembic_version` bookkeeping row lives inside `app_internal` (see
    # migrations_app/env.py), so dropping the schema mid-downgrade would
    # destroy Alembic's own state.
