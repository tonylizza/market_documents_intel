"""passage embeddings and retrieval contexts (Milestone 7B.1)

Revision ID: app_0007
Revises: app_0006
Create Date: 2026-07-29 10:03:39.551471

Adds pgvector-backed deduplicated passage embeddings
(`app.passage_embeddings`, one row per published passage) and
comparison-aware retrieval contexts (`app.retrieval_contexts` plus two
normalized category child tables) implementing the approved "Option C"
architecture: a passage that occupies both sides of two consecutive
comparisons gets one vector and up to two retrieval-context rows, never a
duplicated vector.

`CREATE EXTENSION vector` runs first and is intentionally never dropped on
downgrade -- see the comment in `downgrade()`. This milestone's `current_*`
views live in their own `RETRIEVAL_CURRENT_VIEWS` tuple in
`market_documents.publishing.schema`, deliberately separate from the
`CURRENT_VIEWS` tuple `app_0005`/`app_0006` already replay, so this
migration never has to touch app_0005's history (see that tuple's docstring
for why merging them would break replay).
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa

from market_documents.publishing.schema import (
    CREATE_VECTOR_EXTENSION_SQL,
    DROP_RETRIEVAL_CURRENT_VIEWS_SQL,
    RETRIEVAL_CURRENT_VIEWS,
)

# revision identifiers, used by Alembic.
revision: str = 'app_0007'
down_revision: Union[str, Sequence[str], None] = 'app_0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Fails clearly (not silently) if the target Postgres provider doesn't
    # support pgvector at all -- e.g. a managed host without the extension
    # available raises here rather than later at first INSERT.
    op.execute(CREATE_VECTOR_EXTENSION_SQL)

    op.create_table('passage_embeddings',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('passage_id', sa.UUID(), nullable=False),
    sa.Column('source_embedding_id', sa.UUID(), nullable=False),
    sa.Column('source_embedding_run_id', sa.UUID(), nullable=False),
    sa.Column('embedding_model', sa.String(length=255), nullable=False),
    sa.Column('embedding_model_revision', sa.String(length=64), nullable=False),
    sa.Column('dimensions', sa.Integer(), nullable=False),
    sa.Column('embedding_text_hash', sa.String(length=64), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.Vector(384), nullable=False),
    sa.Column('vector_norm', sa.Float(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['passage_id'], ['app.passages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'passage_id', 'embedding_model', 'embedding_model_revision', name='uq_app_passage_embeddings_scope'),
    schema='app'
    )
    op.create_index('ix_app_passage_embeddings_hnsw_cosine', 'passage_embeddings', ['embedding'], unique=False, schema='app', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_app_passage_embeddings_passage_id', 'passage_embeddings', ['passage_id'], unique=False, schema='app')
    op.create_index('ix_app_passage_embeddings_publication_id', 'passage_embeddings', ['publication_id'], unique=False, schema='app')
    op.create_table('retrieval_contexts',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('passage_id', sa.UUID(), nullable=False),
    sa.Column('passage_embedding_id', sa.UUID(), nullable=False),
    sa.Column('passage_comparison_id', sa.UUID(), nullable=True),
    sa.Column('report_comparison_id', sa.UUID(), nullable=True),
    sa.Column('report_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('context_type', sa.String(length=32), nullable=False),
    sa.Column('report_side', sa.String(length=16), nullable=True),
    sa.Column('alignment_status', sa.String(length=32), nullable=True),
    sa.Column('alignment_type', sa.String(length=32), nullable=True),
    sa.Column('confidence', sa.String(length=32), nullable=True),
    sa.Column('report_period_end', sa.Date(), nullable=True),
    sa.Column('earlier_period_end', sa.Date(), nullable=True),
    sa.Column('later_period_end', sa.Date(), nullable=True),
    sa.Column('heading', sa.Text(), nullable=True),
    sa.Column('passage_type', sa.String(length=32), nullable=False),
    sa.Column('primary_narrative_eligible', sa.Boolean(), nullable=False),
    sa.Column('feature_eligible', sa.Boolean(), nullable=False),
    sa.Column('structured_content_category', sa.String(length=64), nullable=True),
    sa.Column('report_side_quality', sa.String(length=32), nullable=True),
    sa.Column('alignment_change_quality', sa.String(length=32), nullable=True),
    sa.Column('collision_flag', sa.Boolean(), nullable=False),
    sa.Column('split_merge_flag', sa.Boolean(), nullable=False),
    sa.Column('irregular_gap_flag', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(context_type = 'COMPARISON_LINKED' AND passage_comparison_id IS NOT NULL AND report_comparison_id IS NOT NULL AND report_side IS NOT NULL) OR (context_type = 'REPORT_ONLY' AND passage_comparison_id IS NULL AND report_comparison_id IS NULL AND report_side IS NULL)", name='ck_app_retrieval_contexts_type_consistency'),
    sa.CheckConstraint("context_type IN ('COMPARISON_LINKED', 'REPORT_ONLY')", name='ck_app_retrieval_contexts_context_type'),
    sa.ForeignKeyConstraint(['company_id'], ['app.companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['passage_comparison_id'], ['app.passage_comparisons.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['passage_embedding_id'], ['app.passage_embeddings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['passage_id'], ['app.passages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_comparison_id'], ['app.report_comparisons.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['app.reports.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'passage_id', 'passage_comparison_id', 'report_side', 'context_type', name='uq_app_retrieval_contexts_scope', postgresql_nulls_not_distinct=True),
    schema='app'
    )
    op.create_index('ix_app_retrieval_contexts_company_id', 'retrieval_contexts', ['company_id'], unique=False, schema='app')
    op.create_index('ix_app_retrieval_contexts_passage_comparison_id', 'retrieval_contexts', ['passage_comparison_id'], unique=False, schema='app')
    op.create_index('ix_app_retrieval_contexts_passage_embedding_id', 'retrieval_contexts', ['passage_embedding_id'], unique=False, schema='app')
    op.create_index('ix_app_retrieval_contexts_passage_id', 'retrieval_contexts', ['passage_id'], unique=False, schema='app')
    op.create_index('ix_app_retrieval_contexts_publication_id', 'retrieval_contexts', ['publication_id'], unique=False, schema='app')
    op.create_index('ix_app_retrieval_contexts_report_comparison_id', 'retrieval_contexts', ['report_comparison_id'], unique=False, schema='app')
    op.create_index('ix_app_retrieval_contexts_report_id', 'retrieval_contexts', ['report_id'], unique=False, schema='app')
    op.create_table('retrieval_context_language_categories',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('retrieval_context_id', sa.UUID(), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['retrieval_context_id'], ['app.retrieval_contexts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('retrieval_context_id', 'category', name='uq_app_rc_language_categories_scope'),
    schema='app'
    )
    op.create_index('ix_app_rc_language_categories_category', 'retrieval_context_language_categories', ['category'], unique=False, schema='app')
    op.create_index('ix_app_rc_language_categories_context_id', 'retrieval_context_language_categories', ['retrieval_context_id'], unique=False, schema='app')
    op.create_index('ix_app_rc_language_categories_publication_id', 'retrieval_context_language_categories', ['publication_id'], unique=False, schema='app')
    op.create_table('retrieval_context_risk_subcategories',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('retrieval_context_id', sa.UUID(), nullable=False),
    sa.Column('subcategory', sa.String(length=64), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['retrieval_context_id'], ['app.retrieval_contexts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('retrieval_context_id', 'subcategory', name='uq_app_rc_risk_subcategories_scope'),
    schema='app'
    )
    op.create_index('ix_app_rc_risk_subcategories_context_id', 'retrieval_context_risk_subcategories', ['retrieval_context_id'], unique=False, schema='app')
    op.create_index('ix_app_rc_risk_subcategories_publication_id', 'retrieval_context_risk_subcategories', ['publication_id'], unique=False, schema='app')
    op.create_index('ix_app_rc_risk_subcategories_subcategory', 'retrieval_context_risk_subcategories', ['subcategory'], unique=False, schema='app')
    # ### end Alembic commands ###

    for _name, statement in RETRIEVAL_CURRENT_VIEWS:
        op.execute(statement)


def downgrade() -> None:
    """Downgrade schema."""
    for statement in DROP_RETRIEVAL_CURRENT_VIEWS_SQL:
        op.execute(statement)

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('ix_app_rc_risk_subcategories_subcategory', table_name='retrieval_context_risk_subcategories', schema='app')
    op.drop_index('ix_app_rc_risk_subcategories_publication_id', table_name='retrieval_context_risk_subcategories', schema='app')
    op.drop_index('ix_app_rc_risk_subcategories_context_id', table_name='retrieval_context_risk_subcategories', schema='app')
    op.drop_table('retrieval_context_risk_subcategories', schema='app')
    op.drop_index('ix_app_rc_language_categories_publication_id', table_name='retrieval_context_language_categories', schema='app')
    op.drop_index('ix_app_rc_language_categories_context_id', table_name='retrieval_context_language_categories', schema='app')
    op.drop_index('ix_app_rc_language_categories_category', table_name='retrieval_context_language_categories', schema='app')
    op.drop_table('retrieval_context_language_categories', schema='app')
    op.drop_index('ix_app_retrieval_contexts_report_id', table_name='retrieval_contexts', schema='app')
    op.drop_index('ix_app_retrieval_contexts_report_comparison_id', table_name='retrieval_contexts', schema='app')
    op.drop_index('ix_app_retrieval_contexts_publication_id', table_name='retrieval_contexts', schema='app')
    op.drop_index('ix_app_retrieval_contexts_passage_id', table_name='retrieval_contexts', schema='app')
    op.drop_index('ix_app_retrieval_contexts_passage_embedding_id', table_name='retrieval_contexts', schema='app')
    op.drop_index('ix_app_retrieval_contexts_passage_comparison_id', table_name='retrieval_contexts', schema='app')
    op.drop_index('ix_app_retrieval_contexts_company_id', table_name='retrieval_contexts', schema='app')
    op.drop_table('retrieval_contexts', schema='app')
    op.drop_index('ix_app_passage_embeddings_publication_id', table_name='passage_embeddings', schema='app')
    op.drop_index('ix_app_passage_embeddings_passage_id', table_name='passage_embeddings', schema='app')
    op.drop_index('ix_app_passage_embeddings_hnsw_cosine', table_name='passage_embeddings', schema='app', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('passage_embeddings', schema='app')
    # ### end Alembic commands ###

    # `vector` is deliberately never dropped here: it may be a database-wide
    # extension shared by other schemas/objects on a managed provider, and
    # `CREATE EXTENSION IF NOT EXISTS` on a future re-upgrade is a no-op
    # either way. Dropping it is not required to fully reverse this
    # migration's own schema footprint.
