"""app passages and report comparisons

Revision ID: app_0003
Revises: app_0002
Create Date: 2026-07-27 14:49:14.509244

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'app_0003'
down_revision: Union[str, Sequence[str], None] = 'app_0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('passages',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('source_passage_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('report_id', sa.UUID(), nullable=False),
    sa.Column('report_period_end', sa.Date(), nullable=True),
    sa.Column('passage_index', sa.Integer(), nullable=False),
    sa.Column('first_page_number', sa.Integer(), nullable=False),
    sa.Column('last_page_number', sa.Integer(), nullable=False),
    sa.Column('heading', sa.Text(), nullable=True),
    sa.Column('passage_type', sa.String(length=32), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('word_count', sa.Integer(), nullable=False),
    sa.Column('structured_content_category', sa.String(length=64), nullable=True),
    sa.Column('primary_narrative_eligible', sa.Boolean(), nullable=False),
    sa.Column('feature_eligible', sa.Boolean(), nullable=False),
    sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("setweight(to_tsvector('pg_catalog.english', coalesce(heading, '')), 'A') || setweight(to_tsvector('pg_catalog.english', text), 'B')", persisted=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['app.companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['app.reports.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'source_passage_id', name='uq_app_passages_pub_source'),
    schema='app'
    )
    op.create_index('ix_app_passages_company_id', 'passages', ['company_id'], unique=False, schema='app')
    op.create_index('ix_app_passages_publication_id', 'passages', ['publication_id'], unique=False, schema='app')
    op.create_index('ix_app_passages_report_id', 'passages', ['report_id'], unique=False, schema='app')
    op.create_index('ix_app_passages_search_vector', 'passages', ['search_vector'], unique=False, schema='app', postgresql_using='gin')
    op.create_table('report_comparisons',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('source_report_pair_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('earlier_report_id', sa.UUID(), nullable=False),
    sa.Column('later_report_id', sa.UUID(), nullable=False),
    sa.Column('earlier_period_end', sa.Date(), nullable=True),
    sa.Column('later_period_end', sa.Date(), nullable=True),
    sa.Column('gap_months', sa.Integer(), nullable=False),
    sa.Column('chronological_index', sa.Integer(), nullable=False),
    sa.Column('is_transition', sa.Boolean(), nullable=False),
    sa.Column('is_irregular_gap', sa.Boolean(), nullable=False),
    sa.Column('is_latest_for_company', sa.Boolean(), nullable=False),
    sa.Column('is_historical_peak_change', sa.Boolean(), nullable=False),
    sa.Column('disclosure_change_score', sa.Float(), nullable=True),
    sa.Column('disclosure_change_label', sa.String(length=64), nullable=True),
    sa.Column('disclosure_change_percentile', sa.Float(), nullable=True),
    sa.Column('net_tone_change', sa.Float(), nullable=True),
    sa.Column('net_tone_change_label', sa.String(length=64), nullable=True),
    sa.Column('uncertainty_change', sa.Float(), nullable=True),
    sa.Column('uncertainty_change_label', sa.String(length=64), nullable=True),
    sa.Column('risk_introduction_rate', sa.Float(), nullable=True),
    sa.Column('risk_introduction_label', sa.String(length=64), nullable=True),
    sa.Column('risk_removal_rate', sa.Float(), nullable=True),
    sa.Column('risk_removal_label', sa.String(length=64), nullable=True),
    sa.Column('governance_change', sa.Float(), nullable=True),
    sa.Column('governance_change_label', sa.String(length=64), nullable=True),
    sa.Column('financial_condition_change', sa.Float(), nullable=True),
    sa.Column('financial_condition_change_label', sa.String(length=64), nullable=True),
    sa.Column('forward_looking_change', sa.Float(), nullable=True),
    sa.Column('forward_looking_change_label', sa.String(length=64), nullable=True),
    sa.Column('new_passage_count', sa.Integer(), nullable=True),
    sa.Column('removed_passage_count', sa.Integer(), nullable=True),
    sa.Column('lightly_modified_passage_count', sa.Integer(), nullable=True),
    sa.Column('substantially_modified_passage_count', sa.Integer(), nullable=True),
    sa.Column('ambiguous_passage_count', sa.Integer(), nullable=True),
    sa.Column('report_side_quality', sa.String(length=32), nullable=True),
    sa.Column('report_side_quality_label', sa.String(length=64), nullable=True),
    sa.Column('report_side_primary_eligible', sa.Boolean(), nullable=True),
    sa.Column('report_side_warning', sa.Text(), nullable=True),
    sa.Column('alignment_change_quality', sa.String(length=32), nullable=True),
    sa.Column('alignment_change_quality_label', sa.String(length=64), nullable=True),
    sa.Column('alignment_change_primary_eligible', sa.Boolean(), nullable=True),
    sa.Column('alignment_change_warning', sa.Text(), nullable=True),
    sa.Column('dictionary_match_rate_earlier', sa.Float(), nullable=True),
    sa.Column('dictionary_match_rate_later', sa.Float(), nullable=True),
    sa.Column('ambiguous_word_share', sa.Float(), nullable=True),
    sa.Column('collision_flagged_word_share', sa.Float(), nullable=True),
    sa.Column('unmatched_word_share', sa.Float(), nullable=True),
    sa.Column('structured_content_exclusion_share', sa.Float(), nullable=True),
    sa.Column('primary_finding_key', sa.String(length=64), nullable=True),
    sa.Column('secondary_finding_key', sa.String(length=64), nullable=True),
    sa.Column('tertiary_finding_key', sa.String(length=64), nullable=True),
    sa.Column('finding_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['app.companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['earlier_report_id'], ['app.reports.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['later_report_id'], ['app.reports.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'source_report_pair_id', name='uq_app_comparisons_pub_source'),
    schema='app'
    )
    op.create_index('ix_app_comparisons_company_id', 'report_comparisons', ['company_id'], unique=False, schema='app')
    op.create_index('ix_app_comparisons_earlier_report_id', 'report_comparisons', ['earlier_report_id'], unique=False, schema='app')
    op.create_index('ix_app_comparisons_later_report_id', 'report_comparisons', ['later_report_id'], unique=False, schema='app')
    op.create_index('ix_app_comparisons_publication_id', 'report_comparisons', ['publication_id'], unique=False, schema='app')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_app_comparisons_publication_id', table_name='report_comparisons', schema='app')
    op.drop_index('ix_app_comparisons_later_report_id', table_name='report_comparisons', schema='app')
    op.drop_index('ix_app_comparisons_earlier_report_id', table_name='report_comparisons', schema='app')
    op.drop_index('ix_app_comparisons_company_id', table_name='report_comparisons', schema='app')
    op.drop_table('report_comparisons', schema='app')
    op.drop_index('ix_app_passages_search_vector', table_name='passages', schema='app', postgresql_using='gin')
    op.drop_index('ix_app_passages_report_id', table_name='passages', schema='app')
    op.drop_index('ix_app_passages_publication_id', table_name='passages', schema='app')
    op.drop_index('ix_app_passages_company_id', table_name='passages', schema='app')
    op.drop_table('passages', schema='app')
