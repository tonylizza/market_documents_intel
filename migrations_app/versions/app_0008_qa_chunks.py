"""qa chunks (Milestone 7B.2)

Revision ID: app_0008
Revises: app_0007
Create Date: 2026-07-31 08:00:05.942452

Adds the standard-RAG Q&A retrieval corpus: `app.qa_chunks` (one
overlapping ~350-token window per row, one embedding each) and
`app.qa_chunk_passages` (the many-to-many mapping back to the canonical
`app.passages` rows a chunk's character span overlaps). This is a second,
additive vector representation alongside `app.passage_embeddings`
(app_0007) -- it never replaces it, and this migration never touches that
table or the disposable `qa_experiment` schema (a separate, non-Alembic,
non-`app_readonly`-granted schema from the 7B.1d research spike -- see
`docs/qa-retrieval-chunks.md`).

`current_qa_chunks`/`current_qa_chunk_passages` live in their own
`QA_CHUNK_CURRENT_VIEWS` tuple in `market_documents.publishing.schema`,
deliberately separate from `RETRIEVAL_CURRENT_VIEWS` (app_0007) for the same
migration-replay-safety reason documented on that tuple.
"""
from typing import Sequence, Union

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from market_documents.publishing.schema import (
    DROP_QA_CHUNK_CURRENT_VIEWS_SQL,
    QA_CHUNK_CURRENT_VIEWS,
)

# revision identifiers, used by Alembic.
revision: str = 'app_0008'
down_revision: Union[str, Sequence[str], None] = 'app_0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('publications', sa.Column('qa_chunk_count', sa.Integer(), nullable=True), schema='app_internal')
    op.add_column('publications', sa.Column('qa_chunk_passage_mapping_count', sa.Integer(), nullable=True), schema='app_internal')

    op.create_table('qa_chunks',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('report_id', sa.UUID(), nullable=False),
    sa.Column('company_id', sa.UUID(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
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
    sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("setweight(to_tsvector('pg_catalog.english', coalesce(section_heading, '')), 'A') || setweight(to_tsvector('pg_catalog.english', text), 'B')", persisted=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('page_start <= page_end', name='ck_app_qa_chunks_page_range'),
    sa.ForeignKeyConstraint(['company_id'], ['app.companies.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['app.reports.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('publication_id', 'report_id', 'chunk_index', name='uq_app_qa_chunks_pub_report_index'),
    schema='app'
    )
    op.create_index('ix_app_qa_chunks_company_id', 'qa_chunks', ['company_id'], unique=False, schema='app')
    op.create_index('ix_app_qa_chunks_hnsw_cosine', 'qa_chunks', ['embedding'], unique=False, schema='app', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_app_qa_chunks_publication_id', 'qa_chunks', ['publication_id'], unique=False, schema='app')
    op.create_index('ix_app_qa_chunks_report_id', 'qa_chunks', ['report_id'], unique=False, schema='app')

    op.create_table('qa_chunk_passages',
    sa.Column('publication_id', sa.UUID(), nullable=False),
    sa.Column('qa_chunk_id', sa.UUID(), nullable=False),
    sa.Column('passage_id', sa.UUID(), nullable=False),
    sa.Column('member_order', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['passage_id'], ['app.passages.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['publication_id'], ['app_internal.publications.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['qa_chunk_id'], ['app.qa_chunks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('qa_chunk_id', 'passage_id', name='uq_app_qa_chunk_passages_scope'),
    schema='app'
    )
    op.create_index('ix_app_qa_chunk_passages_passage_id', 'qa_chunk_passages', ['passage_id'], unique=False, schema='app')
    op.create_index('ix_app_qa_chunk_passages_publication_id', 'qa_chunk_passages', ['publication_id'], unique=False, schema='app')
    op.create_index('ix_app_qa_chunk_passages_qa_chunk_id', 'qa_chunk_passages', ['qa_chunk_id'], unique=False, schema='app')

    for _name, statement in QA_CHUNK_CURRENT_VIEWS:
        op.execute(statement)


def downgrade() -> None:
    """Downgrade schema."""
    for statement in DROP_QA_CHUNK_CURRENT_VIEWS_SQL:
        op.execute(statement)

    op.drop_index('ix_app_qa_chunk_passages_qa_chunk_id', table_name='qa_chunk_passages', schema='app')
    op.drop_index('ix_app_qa_chunk_passages_publication_id', table_name='qa_chunk_passages', schema='app')
    op.drop_index('ix_app_qa_chunk_passages_passage_id', table_name='qa_chunk_passages', schema='app')
    op.drop_table('qa_chunk_passages', schema='app')

    op.drop_index('ix_app_qa_chunks_report_id', table_name='qa_chunks', schema='app')
    op.drop_index('ix_app_qa_chunks_publication_id', table_name='qa_chunks', schema='app')
    op.drop_index('ix_app_qa_chunks_hnsw_cosine', table_name='qa_chunks', schema='app', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index('ix_app_qa_chunks_company_id', table_name='qa_chunks', schema='app')
    op.drop_table('qa_chunks', schema='app')

    op.drop_column('publications', 'qa_chunk_passage_mapping_count', schema='app_internal')
    op.drop_column('publications', 'qa_chunk_count', schema='app_internal')
