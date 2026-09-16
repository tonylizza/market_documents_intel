"""cutover comparisons (Track 7A.3/7A.4)

Revision ID: app_0009
Revises: app_0008
Create Date: 2026-09-16 00:00:00.000000

Adds `app.narrative_unit_comparisons` and `app.structured_table_comparisons`:
Track 7C.6 semantic-unit / structured-table comparison results, persisted at
publish time for report comparisons in the fixed cutover scope
(`market_documents.services.cutover_config`). These are always computed with
the cutover router force-enabled, independent of the live
`SEMANTIC_COMPARISON_CUTOVER_ENABLED` flag at publish time -- the live web
application decides at read time, from its own copy of that flag, whether to
prefer these rows over the legacy `app.report_comparisons` fields. See
docs/7a3-7a4-live-comparison-integration.md.

`current_narrative_unit_comparisons`/`current_structured_table_comparisons`
live in their own `CUTOVER_COMPARISON_CURRENT_VIEWS` tuple in
`market_documents.publishing.schema`, deliberately separate from
`QA_CHUNK_CURRENT_VIEWS` (app_0008) for the same migration-replay-safety
reason documented on that tuple.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from market_documents.publishing.schema import (
    CUTOVER_COMPARISON_CURRENT_VIEWS,
    DROP_CUTOVER_COMPARISON_CURRENT_VIEWS_SQL,
)

# revision identifiers, used by Alembic.
revision: str = 'app_0009'
down_revision: Union[str, Sequence[str], None] = 'app_0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('publications', sa.Column('narrative_comparison_count', sa.Integer(), nullable=True), schema='app_internal')
    op.add_column('publications', sa.Column('structured_comparison_count', sa.Integer(), nullable=True), schema='app_internal')

    op.create_table('narrative_unit_comparisons',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('report_comparison_id', sa.UUID(), nullable=False),
    sa.Column('schedule', sa.String(length=64), nullable=False),
    sa.Column('unit_key', sa.String(length=128), nullable=False),
    sa.Column('comparison_backend', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('alignment_status', sa.String(length=32), nullable=True),
    sa.Column('alignment_confidence', sa.String(length=32), nullable=True),
    sa.Column('analytical_mode', sa.String(length=32), nullable=True),
    sa.Column('lexical_metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('earlier_word_count', sa.Integer(), nullable=True),
    sa.Column('later_word_count', sa.Integer(), nullable=True),
    sa.Column('earlier_provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('later_provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('review_reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_comparison_id'], ['app.report_comparisons.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'report_comparison_id', 'unit_key', name='uq_app_narrative_unit_comparisons_scope'),
    schema='app'
    )
    op.create_index('ix_app_narrative_unit_comparisons_comparison_id', 'narrative_unit_comparisons', ['report_comparison_id'], unique=False, schema='app')
    op.create_index('ix_app_narrative_unit_comparisons_publication_id', 'narrative_unit_comparisons', ['publication_id'], unique=False, schema='app')

    op.create_table('structured_table_comparisons',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('report_comparison_id', sa.UUID(), nullable=False),
    sa.Column('table_family_key', sa.String(length=128), nullable=False),
    sa.Column('comparison_backend', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('row_alignments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('column_alignments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('value_change_events', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('footnotes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('earlier_provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('later_provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('review_reason', sa.Text(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_comparison_id'], ['app.report_comparisons.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'report_comparison_id', 'table_family_key', name='uq_app_structured_table_comparisons_scope'),
    schema='app'
    )
    op.create_index('ix_app_structured_table_comparisons_comparison_id', 'structured_table_comparisons', ['report_comparison_id'], unique=False, schema='app')
    op.create_index('ix_app_structured_table_comparisons_publication_id', 'structured_table_comparisons', ['publication_id'], unique=False, schema='app')

    for _name, statement in CUTOVER_COMPARISON_CURRENT_VIEWS:
        op.execute(statement)


def downgrade() -> None:
    """Downgrade schema."""
    for statement in DROP_CUTOVER_COMPARISON_CURRENT_VIEWS_SQL:
        op.execute(statement)

    op.drop_index('ix_app_structured_table_comparisons_publication_id', table_name='structured_table_comparisons', schema='app')
    op.drop_index('ix_app_structured_table_comparisons_comparison_id', table_name='structured_table_comparisons', schema='app')
    op.drop_table('structured_table_comparisons', schema='app')

    op.drop_index('ix_app_narrative_unit_comparisons_publication_id', table_name='narrative_unit_comparisons', schema='app')
    op.drop_index('ix_app_narrative_unit_comparisons_comparison_id', table_name='narrative_unit_comparisons', schema='app')
    op.drop_table('narrative_unit_comparisons', schema='app')

    op.drop_column('publications', 'structured_comparison_count', schema='app_internal')
    op.drop_column('publications', 'narrative_comparison_count', schema='app_internal')
