"""app language metrics, passage comparisons, passage language signals, discovery items

Revision ID: app_0004
Revises: app_0003
Create Date: 2026-07-27 14:49:14.509244

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'app_0004'
down_revision: Union[str, Sequence[str], None] = 'app_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('discovery_items',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('report_comparison_id', sa.UUID(), nullable=False),
    sa.Column('discovery_type', sa.String(length=64), nullable=False),
    sa.Column('rank_scope', sa.String(length=32), nullable=False),
    sa.Column('score', sa.Float(), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('percentile', sa.Float(), nullable=True),
    sa.Column('finding_key', sa.String(length=64), nullable=False),
    sa.Column('supporting_metric_key', sa.String(length=64), nullable=False),
    sa.Column('supporting_value', sa.Float(), nullable=False),
    sa.Column('supporting_unit', sa.String(length=32), nullable=False),
    sa.Column('quality_label', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['app.companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_comparison_id'], ['app.report_comparisons.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'discovery_type', 'rank_scope', 'report_comparison_id', name='uq_app_discovery_items_scope'),
    schema='app'
    )
    op.create_index('ix_app_discovery_items_company_id', 'discovery_items', ['company_id'], unique=False, schema='app')
    op.create_index('ix_app_discovery_items_publication_id', 'discovery_items', ['publication_id'], unique=False, schema='app')
    op.create_index('ix_app_discovery_items_type_scope_rank', 'discovery_items', ['discovery_type', 'rank_scope', 'rank'], unique=False, schema='app')
    op.create_table('language_metrics',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('report_comparison_id', sa.UUID(), nullable=False),
    sa.Column('metric_scope', sa.String(length=32), nullable=False),
    sa.Column('population', sa.String(length=64), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('subcategory', sa.String(length=64), nullable=True),
    sa.Column('earlier_count', sa.Integer(), nullable=True),
    sa.Column('later_count', sa.Integer(), nullable=True),
    sa.Column('earlier_rate_per_1000', sa.Float(), nullable=True),
    sa.Column('later_rate_per_1000', sa.Float(), nullable=True),
    sa.Column('rate_change', sa.Float(), nullable=True),
    sa.Column('absolute_rate_change', sa.Float(), nullable=True),
    sa.Column('introduced_count', sa.Integer(), nullable=True),
    sa.Column('introduced_rate_per_1000', sa.Float(), nullable=True),
    sa.Column('removed_count', sa.Integer(), nullable=True),
    sa.Column('removed_rate_per_1000', sa.Float(), nullable=True),
    sa.Column('retained_count', sa.Integer(), nullable=True),
    sa.Column('negated_count', sa.Integer(), nullable=True),
    sa.Column('quality', sa.String(length=32), nullable=True),
    sa.Column('primary_eligible', sa.Boolean(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_comparison_id'], ['app.report_comparisons.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'report_comparison_id', 'metric_scope', 'population', 'category', 'subcategory', name='uq_app_language_metrics_scope'),
    schema='app'
    )
    op.create_index('ix_app_language_metrics_comparison_id', 'language_metrics', ['report_comparison_id'], unique=False, schema='app')
    op.create_index('ix_app_language_metrics_publication_id', 'language_metrics', ['publication_id'], unique=False, schema='app')
    op.create_index('ix_app_language_metrics_scope_category', 'language_metrics', ['metric_scope', 'category'], unique=False, schema='app')
    op.create_table('passage_comparisons',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('source_alignment_id', sa.UUID(), nullable=False),
    sa.Column('report_comparison_id', sa.UUID(), nullable=False),
    sa.Column('earlier_passage_id', sa.UUID(), nullable=True),
    sa.Column('later_passage_id', sa.UUID(), nullable=True),
    sa.Column('alignment_status', sa.String(length=32), nullable=False),
    sa.Column('alignment_type', sa.String(length=32), nullable=False),
    sa.Column('confidence', sa.String(length=32), nullable=False),
    sa.Column('confidence_label', sa.String(length=64), nullable=False),
    sa.Column('semantic_similarity', sa.Float(), nullable=True),
    sa.Column('lexical_similarity', sa.Float(), nullable=True),
    sa.Column('heading_similarity', sa.Float(), nullable=True),
    sa.Column('content_score', sa.Float(), nullable=True),
    sa.Column('position_difference', sa.Float(), nullable=True),
    sa.Column('collision_flag', sa.Boolean(), nullable=False),
    sa.Column('split_merge_flag', sa.Boolean(), nullable=False),
    sa.Column('primary_alignment', sa.Boolean(), nullable=False),
    sa.Column('review_reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('earlier_passage_id IS NOT NULL OR later_passage_id IS NOT NULL', name='ck_app_passage_comparisons_one_side_present'),
    sa.ForeignKeyConstraint(['earlier_passage_id'], ['app.passages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['later_passage_id'], ['app.passages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_comparison_id'], ['app.report_comparisons.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'source_alignment_id', name='uq_app_passage_comparisons_pub_source'),
    schema='app'
    )
    op.create_index('ix_app_passage_comparisons_earlier_passage_id', 'passage_comparisons', ['earlier_passage_id'], unique=False, schema='app')
    op.create_index('ix_app_passage_comparisons_later_passage_id', 'passage_comparisons', ['later_passage_id'], unique=False, schema='app')
    op.create_index('ix_app_passage_comparisons_publication_id', 'passage_comparisons', ['publication_id'], unique=False, schema='app')
    op.create_index('ix_app_passage_comparisons_report_comparison_id', 'passage_comparisons', ['report_comparison_id'], unique=False, schema='app')
    op.create_table('passage_language_signals',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('passage_id', sa.UUID(), nullable=False),
    sa.Column('passage_comparison_id', sa.UUID(), nullable=False),
    sa.Column('report_comparison_id', sa.UUID(), nullable=False),
    sa.Column('report_side', sa.String(length=16), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('subcategory', sa.String(length=64), nullable=True),
    sa.Column('raw_count', sa.Integer(), nullable=False),
    sa.Column('negated_count', sa.Integer(), nullable=True),
    sa.Column('adjusted_count', sa.Integer(), nullable=False),
    sa.Column('rate_per_1000', sa.Float(), nullable=True),
    sa.Column('is_introduced', sa.Boolean(), nullable=False),
    sa.Column('is_removed', sa.Boolean(), nullable=False),
    sa.Column('is_retained', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['passage_comparison_id'], ['app.passage_comparisons.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['passage_id'], ['app.passages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_comparison_id'], ['app.report_comparisons.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'passage_comparison_id', 'report_side', 'category', 'subcategory', name='uq_app_passage_language_signals_scope'),
    schema='app'
    )
    op.create_index('ix_app_passage_language_signals_comparison_id', 'passage_language_signals', ['report_comparison_id'], unique=False, schema='app')
    op.create_index('ix_app_passage_language_signals_passage_comparison_id', 'passage_language_signals', ['passage_comparison_id'], unique=False, schema='app')
    op.create_index('ix_app_passage_language_signals_passage_id', 'passage_language_signals', ['passage_id'], unique=False, schema='app')
    op.create_index('ix_app_passage_language_signals_publication_id', 'passage_language_signals', ['publication_id'], unique=False, schema='app')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_app_passage_language_signals_publication_id', table_name='passage_language_signals', schema='app')
    op.drop_index('ix_app_passage_language_signals_passage_id', table_name='passage_language_signals', schema='app')
    op.drop_index('ix_app_passage_language_signals_passage_comparison_id', table_name='passage_language_signals', schema='app')
    op.drop_index('ix_app_passage_language_signals_comparison_id', table_name='passage_language_signals', schema='app')
    op.drop_table('passage_language_signals', schema='app')
    op.drop_index('ix_app_passage_comparisons_report_comparison_id', table_name='passage_comparisons', schema='app')
    op.drop_index('ix_app_passage_comparisons_publication_id', table_name='passage_comparisons', schema='app')
    op.drop_index('ix_app_passage_comparisons_later_passage_id', table_name='passage_comparisons', schema='app')
    op.drop_index('ix_app_passage_comparisons_earlier_passage_id', table_name='passage_comparisons', schema='app')
    op.drop_table('passage_comparisons', schema='app')
    op.drop_index('ix_app_language_metrics_scope_category', table_name='language_metrics', schema='app')
    op.drop_index('ix_app_language_metrics_publication_id', table_name='language_metrics', schema='app')
    op.drop_index('ix_app_language_metrics_comparison_id', table_name='language_metrics', schema='app')
    op.drop_table('language_metrics', schema='app')
    op.drop_index('ix_app_discovery_items_type_scope_rank', table_name='discovery_items', schema='app')
    op.drop_index('ix_app_discovery_items_publication_id', table_name='discovery_items', schema='app')
    op.drop_index('ix_app_discovery_items_company_id', table_name='discovery_items', schema='app')
    op.drop_table('discovery_items', schema='app')
