"""versioned shared artifacts (Track 7F.7a.5)

Revision ID: app_0014
Revises: app_0013
Create Date: 2026-09-23 00:00:00.000000

Tracks 7F.7a.4/7F.7a.4a designed (but never applied) a shared, independently
-versioned `app_artifacts` schema for the four large publication-scoped
families that were measured 100% content-identical across recent real
releases (passage_comparisons, retrieval_contexts + children,
passage_language_signals, qa_chunks + qa_chunk_passages) -- see
docs/versioned-shared-publication-artifacts-design-7f7a4.md and
docs/shared-artifact-migration-bootstrap-7f7a4a.md. 7F.7a.4a additionally
found that migrating PRODUCTION in place cannot fit under the 512MB Neon
cap (the additive backfill phase alone peaks near 712MB) and recommended a
fresh-Neon-project cutover instead, built natively against this schema.

This migration implements the schema and qualification-track (7F.7a.5)
LOCALLY only -- it never runs against production. It follows the exact
additive, backward-compatible template Track 7E.1's `app_0010` already
established for `app_corpus`: new tables are added, a `*_artifact_id`
column is added to each thin per-publication table, that table's own bulk
content columns are relaxed to nullable (existing populated rows are left
untouched), and the affected `current_*` views are redefined via
`CREATE OR REPLACE VIEW` to resolve content through `COALESCE(t.<col>,
art.<col>)` -- a publication built before this migration keeps working
unchanged (COALESCE prefers its own populated columns); a publication built
from this migration onward writes NULL into these columns and an
`*_artifact_id` FK instead, so unchanged source content is written to
`app_artifacts` at most once no matter how many publications reference it.

Deliberately in scope: `passage_comparisons`, `retrieval_contexts`,
`passage_language_signals`, `qa_chunks` (4 view rewrites -- see
`ARTIFACT_CURRENT_VIEWS`'s module docstring in `publishing/schema.py` for
why `retrieval_context_language_categories`, `retrieval_context_risk_
subcategories`, and `qa_chunk_passages` get `app_artifacts` counterparts +
a link column, for GC/reuse-provenance symmetry, but no view rewrite: their
entire content is one small column, not worth the read-time join).

No data is backfilled by this migration (unlike app_0010): all four
families are ADDITIVE new tables with nothing existing to backfill *from*
into a publication-independent shape -- a pre-existing local publication's
own `app.*` rows already hold their full content inline and keep resolving
through it via COALESCE; only publications built from this migration
onward ever populate `app_artifacts`.
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from market_documents.publishing.schema import ARTIFACT_CURRENT_VIEWS, CREATE_ARTIFACTS_SCHEMA_SQL

# revision identifiers, used by Alembic.
revision: str = 'app_0014'
down_revision: Union[str, Sequence[str], None] = 'app_0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(CREATE_ARTIFACTS_SCHEMA_SQL)

    op.add_column(
        'publications', sa.Column('alignment_artifact_version', sa.String(length=64), nullable=True),
        schema='app_internal',
    )
    op.add_column(
        'publications', sa.Column('language_signal_artifact_version', sa.String(length=64), nullable=True),
        schema='app_internal',
    )
    op.add_column(
        'publications', sa.Column('qa_chunking_artifact_version', sa.String(length=64), nullable=True),
        schema='app_internal',
    )

    # --- app_artifacts.passage_comparisons ---
    op.create_table(
        'passage_comparisons',
        sa.Column('source_alignment_id', sa.UUID(), nullable=False),
        sa.Column('alignment_artifact_version', sa.String(length=64), nullable=False),
        sa.Column('earlier_source_passage_id', sa.UUID(), nullable=True),
        sa.Column('later_source_passage_id', sa.UUID(), nullable=True),
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
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_alignment_id', 'alignment_artifact_version',
            name='uq_app_artifacts_passage_comparisons_source_version',
        ),
        schema='app_artifacts',
    )
    op.create_index(
        'ix_app_artifacts_passage_comparisons_source', 'passage_comparisons', ['source_alignment_id'],
        unique=False, schema='app_artifacts',
    )

    # --- app_artifacts.retrieval_contexts (+ children) ---
    op.create_table(
        'retrieval_contexts',
        sa.Column('source_key', sa.String(length=64), nullable=False),
        sa.Column('report_side', sa.String(length=16), nullable=True),
        sa.Column('context_type', sa.String(length=32), nullable=False),
        sa.Column('alignment_artifact_version', sa.String(length=64), nullable=False),
        sa.Column('source_passage_id', sa.UUID(), nullable=False),
        sa.Column('alignment_status', sa.String(length=32), nullable=True),
        sa.Column('alignment_type', sa.String(length=32), nullable=True),
        sa.Column('confidence', sa.String(length=32), nullable=True),
        sa.Column('heading', sa.Text(), nullable=True),
        sa.Column('passage_type', sa.String(length=32), nullable=False),
        sa.Column('primary_narrative_eligible', sa.Boolean(), nullable=False),
        sa.Column('feature_eligible', sa.Boolean(), nullable=False),
        sa.Column('structured_content_category', sa.String(length=64), nullable=True),
        sa.Column('collision_flag', sa.Boolean(), nullable=False),
        sa.Column('split_merge_flag', sa.Boolean(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_key', 'report_side', 'context_type', 'alignment_artifact_version',
            name='uq_app_artifacts_retrieval_contexts_scope', postgresql_nulls_not_distinct=True,
        ),
        schema='app_artifacts',
    )
    op.create_index(
        'ix_app_artifacts_retrieval_contexts_source_key', 'retrieval_contexts', ['source_key'],
        unique=False, schema='app_artifacts',
    )

    op.create_table(
        'retrieval_context_language_categories',
        sa.Column('retrieval_context_artifact_id', sa.UUID(), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['retrieval_context_artifact_id'], ['app_artifacts.retrieval_contexts.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'retrieval_context_artifact_id', 'category', name='uq_app_artifacts_rc_language_categories_scope'
        ),
        schema='app_artifacts',
    )
    op.create_table(
        'retrieval_context_risk_subcategories',
        sa.Column('retrieval_context_artifact_id', sa.UUID(), nullable=False),
        sa.Column('subcategory', sa.String(length=64), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(
            ['retrieval_context_artifact_id'], ['app_artifacts.retrieval_contexts.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'retrieval_context_artifact_id', 'subcategory', name='uq_app_artifacts_rc_risk_subcategories_scope'
        ),
        schema='app_artifacts',
    )

    # --- app_artifacts.passage_language_signals ---
    op.create_table(
        'passage_language_signals',
        sa.Column('source_signal_id', sa.UUID(), nullable=False),
        sa.Column('report_side', sa.String(length=16), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('subcategory', sa.String(length=64), nullable=True),
        sa.Column('language_signal_artifact_version', sa.String(length=64), nullable=False),
        sa.Column('raw_count', sa.Integer(), nullable=False),
        sa.Column('negated_count', sa.Integer(), nullable=True),
        sa.Column('adjusted_count', sa.Integer(), nullable=False),
        sa.Column('rate_per_1000', sa.Float(), nullable=True),
        sa.Column('is_introduced', sa.Boolean(), nullable=False),
        sa.Column('is_removed', sa.Boolean(), nullable=False),
        sa.Column('is_retained', sa.Boolean(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_signal_id', 'report_side', 'category', 'subcategory', 'language_signal_artifact_version',
            name='uq_app_artifacts_passage_language_signals_scope', postgresql_nulls_not_distinct=True,
        ),
        schema='app_artifacts',
    )
    op.create_index(
        'ix_app_artifacts_passage_language_signals_source', 'passage_language_signals', ['source_signal_id'],
        unique=False, schema='app_artifacts',
    )

    # --- app_artifacts.qa_chunks (+ qa_chunk_passages) ---
    op.create_table(
        'qa_chunks',
        sa.Column('source_report_id', sa.UUID(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('qa_chunking_artifact_version', sa.String(length=64), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('section_heading', sa.Text(), nullable=True),
        sa.Column('page_start', sa.Integer(), nullable=False),
        sa.Column('page_end', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('truncation_policy', sa.String(length=32), nullable=False),
        sa.Column('embedding_model', sa.String(length=255), nullable=False),
        sa.Column('embedding_model_revision', sa.String(length=64), nullable=False),
        sa.Column('dimensions', sa.Integer(), nullable=False),
        sa.Column('embedding_text_hash', sa.String(length=64), nullable=False),
        sa.Column('embedding', pgvector.sqlalchemy.Vector(384), nullable=False),
        sa.Column('vector_norm', sa.Float(), nullable=False),
        sa.Column(
            'search_vector', postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('pg_catalog.english', coalesce(section_heading, '')), 'A') || "
                "setweight(to_tsvector('pg_catalog.english', text), 'B')",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('page_start <= page_end', name='ck_app_artifacts_qa_chunks_page_range'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_report_id', 'chunk_index', 'qa_chunking_artifact_version',
            'embedding_model', 'embedding_model_revision', name='uq_app_artifacts_qa_chunks_scope',
        ),
        schema='app_artifacts',
    )
    op.create_index(
        'ix_app_artifacts_qa_chunks_source_report_id', 'qa_chunks', ['source_report_id'],
        unique=False, schema='app_artifacts',
    )
    op.create_index(
        'ix_app_artifacts_qa_chunks_hnsw_cosine', 'qa_chunks', ['embedding'], unique=False, schema='app_artifacts',
        postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.create_table(
        'qa_chunk_passages',
        sa.Column('qa_chunk_artifact_id', sa.UUID(), nullable=False),
        sa.Column('source_member_passage_id', sa.UUID(), nullable=False),
        sa.Column('member_order', sa.Integer(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['qa_chunk_artifact_id'], ['app_artifacts.qa_chunks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'qa_chunk_artifact_id', 'source_member_passage_id', name='uq_app_artifacts_qa_chunk_passages_scope'
        ),
        schema='app_artifacts',
    )

    # --- thin `app.*` tables: add link columns, relax content to nullable ---
    op.add_column(
        'passage_comparisons',
        sa.Column('alignment_artifact_id', sa.UUID(), nullable=True),
        schema='app',
    )
    op.create_foreign_key(
        'passage_comparisons_alignment_artifact_id_fkey', 'passage_comparisons', 'passage_comparisons',
        ['alignment_artifact_id'], ['id'], source_schema='app', referent_schema='app_artifacts',
    )
    for col in ('alignment_status', 'alignment_type', 'confidence', 'confidence_label',
                'collision_flag', 'split_merge_flag', 'primary_alignment'):
        op.alter_column('passage_comparisons', col, nullable=True, schema='app')

    op.add_column('retrieval_contexts', sa.Column('alignment_artifact_id', sa.UUID(), nullable=True), schema='app')
    op.create_foreign_key(
        'retrieval_contexts_alignment_artifact_id_fkey', 'retrieval_contexts', 'retrieval_contexts',
        ['alignment_artifact_id'], ['id'], source_schema='app', referent_schema='app_artifacts',
    )
    for col in ('passage_type', 'primary_narrative_eligible', 'feature_eligible',
                'collision_flag', 'split_merge_flag'):
        op.alter_column('retrieval_contexts', col, nullable=True, schema='app')

    op.add_column(
        'retrieval_context_language_categories',
        sa.Column('retrieval_context_artifact_id', sa.UUID(), nullable=True),
        schema='app',
    )
    op.create_foreign_key(
        'rc_language_categories_artifact_id_fkey', 'retrieval_context_language_categories',
        'retrieval_context_language_categories', ['retrieval_context_artifact_id'], ['id'],
        source_schema='app', referent_schema='app_artifacts',
    )
    op.add_column(
        'retrieval_context_risk_subcategories',
        sa.Column('retrieval_context_artifact_id', sa.UUID(), nullable=True),
        schema='app',
    )
    op.create_foreign_key(
        'rc_risk_subcategories_artifact_id_fkey', 'retrieval_context_risk_subcategories',
        'retrieval_context_risk_subcategories', ['retrieval_context_artifact_id'], ['id'],
        source_schema='app', referent_schema='app_artifacts',
    )

    op.add_column(
        'passage_language_signals',
        sa.Column('language_signal_artifact_id', sa.UUID(), nullable=True),
        schema='app',
    )
    op.create_foreign_key(
        'passage_language_signals_artifact_id_fkey', 'passage_language_signals', 'passage_language_signals',
        ['language_signal_artifact_id'], ['id'], source_schema='app', referent_schema='app_artifacts',
    )
    for col in ('raw_count', 'adjusted_count', 'is_introduced', 'is_removed', 'is_retained'):
        op.alter_column('passage_language_signals', col, nullable=True, schema='app')

    op.add_column('qa_chunks', sa.Column('qa_chunking_artifact_id', sa.UUID(), nullable=True), schema='app')
    op.create_foreign_key(
        'qa_chunks_artifact_id_fkey', 'qa_chunks', 'qa_chunks',
        ['qa_chunking_artifact_id'], ['id'], source_schema='app', referent_schema='app_artifacts',
    )
    for col in ('text', 'page_start', 'page_end', 'token_count', 'truncation_policy',
                'embedding_model', 'embedding_model_revision', 'dimensions', 'embedding_text_hash',
                'embedding', 'vector_norm'):
        op.alter_column('qa_chunks', col, nullable=True, schema='app')

    op.add_column(
        'qa_chunk_passages',
        sa.Column('qa_chunk_passage_artifact_id', sa.UUID(), nullable=True),
        schema='app',
    )
    op.create_foreign_key(
        'qa_chunk_passages_artifact_id_fkey', 'qa_chunk_passages', 'qa_chunk_passages',
        ['qa_chunk_passage_artifact_id'], ['id'], source_schema='app', referent_schema='app_artifacts',
    )

    for _name, statement in ARTIFACT_CURRENT_VIEWS:
        op.execute(statement)


def downgrade() -> None:
    """Downgrade schema.

    Order matters here, the reverse of the usual reason: the legacy
    (pre-app_0014) view definitions are all bare `SELECT t.* FROM app.<table>
    t ...` -- restoring them BEFORE the new `*_artifact_id` columns are
    dropped would make that `t.*` pick up the still-present new column too,
    and Postgres then refuses to drop a column a view depends on. So every
    new column is dropped first (while the app_0014 COALESCE views that
    already reference it by name are still in place -- dropping a view
    column they name is fine, only `t.*` is the trap), and only then are the
    legacy views recreated against the now-fully-reverted table shape.
    """
    for statement in _DROP_ARTIFACT_CURRENT_VIEWS_SQL_LOCAL:
        op.execute(statement)

    op.drop_constraint('qa_chunk_passages_artifact_id_fkey', 'qa_chunk_passages', schema='app', type_='foreignkey')
    op.drop_column('qa_chunk_passages', 'qa_chunk_passage_artifact_id', schema='app')

    for col in ('text', 'page_start', 'page_end', 'token_count', 'truncation_policy',
                'embedding_model', 'embedding_model_revision', 'dimensions', 'embedding_text_hash',
                'embedding', 'vector_norm'):
        op.alter_column('qa_chunks', col, nullable=False, schema='app')
    op.drop_constraint('qa_chunks_artifact_id_fkey', 'qa_chunks', schema='app', type_='foreignkey')
    op.drop_column('qa_chunks', 'qa_chunking_artifact_id', schema='app')

    for col in ('raw_count', 'adjusted_count', 'is_introduced', 'is_removed', 'is_retained'):
        op.alter_column('passage_language_signals', col, nullable=False, schema='app')
    op.drop_constraint(
        'passage_language_signals_artifact_id_fkey', 'passage_language_signals', schema='app', type_='foreignkey'
    )
    op.drop_column('passage_language_signals', 'language_signal_artifact_id', schema='app')

    op.drop_constraint(
        'rc_risk_subcategories_artifact_id_fkey', 'retrieval_context_risk_subcategories',
        schema='app', type_='foreignkey',
    )
    op.drop_column('retrieval_context_risk_subcategories', 'retrieval_context_artifact_id', schema='app')
    op.drop_constraint(
        'rc_language_categories_artifact_id_fkey', 'retrieval_context_language_categories',
        schema='app', type_='foreignkey',
    )
    op.drop_column('retrieval_context_language_categories', 'retrieval_context_artifact_id', schema='app')

    for col in ('passage_type', 'primary_narrative_eligible', 'feature_eligible',
                'collision_flag', 'split_merge_flag'):
        op.alter_column('retrieval_contexts', col, nullable=False, schema='app')
    op.drop_constraint(
        'retrieval_contexts_alignment_artifact_id_fkey', 'retrieval_contexts', schema='app', type_='foreignkey'
    )
    op.drop_column('retrieval_contexts', 'alignment_artifact_id', schema='app')

    for col in ('alignment_status', 'alignment_type', 'confidence', 'confidence_label',
                'collision_flag', 'split_merge_flag', 'primary_alignment'):
        op.alter_column('passage_comparisons', col, nullable=False, schema='app')
    op.drop_constraint(
        'passage_comparisons_alignment_artifact_id_fkey', 'passage_comparisons', schema='app', type_='foreignkey'
    )
    op.drop_column('passage_comparisons', 'alignment_artifact_id', schema='app')

    from market_documents.publishing.schema import CURRENT_VIEWS, QA_CHUNK_CURRENT_VIEWS, RETRIEVAL_CURRENT_VIEWS

    for name, statement in CURRENT_VIEWS:
        if name in ("current_passage_comparisons", "current_passage_language_signals"):
            op.execute(statement)
    for name, statement in RETRIEVAL_CURRENT_VIEWS:
        if name == "current_retrieval_contexts":
            op.execute(statement)
    for name, statement in QA_CHUNK_CURRENT_VIEWS:
        if name == "current_qa_chunks":
            op.execute(statement)

    op.drop_table('qa_chunk_passages', schema='app_artifacts')
    op.drop_index('ix_app_artifacts_qa_chunks_hnsw_cosine', table_name='qa_chunks', schema='app_artifacts',
                   postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index('ix_app_artifacts_qa_chunks_source_report_id', table_name='qa_chunks', schema='app_artifacts')
    op.drop_table('qa_chunks', schema='app_artifacts')

    op.drop_index(
        'ix_app_artifacts_passage_language_signals_source', table_name='passage_language_signals',
        schema='app_artifacts',
    )
    op.drop_table('passage_language_signals', schema='app_artifacts')

    op.drop_table('retrieval_context_risk_subcategories', schema='app_artifacts')
    op.drop_table('retrieval_context_language_categories', schema='app_artifacts')
    op.drop_index('ix_app_artifacts_retrieval_contexts_source_key', table_name='retrieval_contexts',
                  schema='app_artifacts')
    op.drop_table('retrieval_contexts', schema='app_artifacts')

    op.drop_index(
        'ix_app_artifacts_passage_comparisons_source', table_name='passage_comparisons', schema='app_artifacts'
    )
    op.drop_table('passage_comparisons', schema='app_artifacts')

    op.drop_column('publications', 'qa_chunking_artifact_version', schema='app_internal')
    op.drop_column('publications', 'language_signal_artifact_version', schema='app_internal')
    op.drop_column('publications', 'alignment_artifact_version', schema='app_internal')

    # `app_artifacts` schema itself is deliberately never dropped -- same
    # reasoning as `vector` extension in app_0007's downgrade: harmless to
    # leave an empty schema behind, and `CREATE SCHEMA IF NOT EXISTS` on a
    # future re-upgrade is a no-op either way.


_DROP_ARTIFACT_CURRENT_VIEWS_SQL_LOCAL = (
    "DROP VIEW IF EXISTS app.current_qa_chunks;",
    "DROP VIEW IF EXISTS app.current_passage_language_signals;",
    "DROP VIEW IF EXISTS app.current_retrieval_contexts;",
    "DROP VIEW IF EXISTS app.current_passage_comparisons;",
)
