"""oversized passage retrieval subchunks and block-split provenance

Milestone 6 (see docs/oversized-passage-retrieval-subchunks-experiment.md):

1. `passage_retrieval_chunks`: retrieval-only embeddings for a passage whose
   full text exceeds the embedding model's token limit. The canonical
   `Passage` is unchanged; this table exists purely so an oversized
   passage can still be nominated as a semantic candidate.
2. `embedding_runs.oversized_chunked_passage_count` /
   `retrieval_chunk_count`: distinct from the pre-existing
   `skipped_passage_count` (now reserved for genuine failures) -- a
   chunked passage is retrievable, not silently invisible.
3. `passage_source_blocks.source_char_start` / `source_char_end`: the
   oversized-single-block segmentation fix can now split one TextBlock's
   text across more than one Passage; the old
   `uq_passage_source_blocks_run_text_block` constraint assumed one block
   belongs to exactly one passage per run and is replaced by a
   span-keyed constraint. Existing rows are backfilled to the full-block
   span `(0, len(text))`, identical in meaning to their pre-migration
   one-row-per-block state.
4. `passage_alignments.semantic_similarity_basis`: records whether a row's
   `semantic_similarity` is a true canonical-embedding cosine or a
   retrieval-chunk max-similarity proxy (a different, documented quantity
   -- see `alignment_candidates.CandidateMatch`). Nullable; existing rows
   are left NULL (interpreted as canonical, the only kind that existed
   before this migration).

Revision ID: ce5dc703671d
Revises: 59387e85ca06
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = 'ce5dc703671d'
down_revision: Union[str, Sequence[str], None] = '59387e85ca06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. passage_retrieval_chunks
    op.create_table(
        'passage_retrieval_chunks',
        sa.Column('embedding_run_id', sa.UUID(), nullable=False),
        sa.Column('passage_id', sa.UUID(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('chunk_text', sa.Text(), nullable=False),
        sa.Column('char_start', sa.Integer(), nullable=False),
        sa.Column('char_end', sa.Integer(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['embedding_run_id'], ['embedding_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['passage_id'], ['passages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'embedding_run_id', 'passage_id', 'chunk_index', name='uq_passage_retrieval_chunks_run_passage_chunk'
        ),
    )
    op.create_index(
        'ix_passage_retrieval_chunks_passage_id', 'passage_retrieval_chunks', ['passage_id'], unique=False
    )
    op.create_index(
        'ix_passage_retrieval_chunks_embedding_run_id', 'passage_retrieval_chunks', ['embedding_run_id'],
        unique=False,
    )
    # Mirrors ix_passage_embeddings_embedding_hnsw_cosine (2ee4738d0d76):
    # retained for future unrestricted search, not the default query path
    # (get_semantic_candidates guards its own subchunk query with the same
    # `SET LOCAL enable_indexscan/enable_bitmapscan = off` pattern used for
    # the canonical-embedding query).
    op.create_index(
        'ix_passage_retrieval_chunks_embedding_hnsw_cosine',
        'passage_retrieval_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )

    # 2. embedding_runs: new counters, distinct from skipped_passage_count
    op.add_column('embedding_runs', sa.Column('oversized_chunked_passage_count', sa.Integer(), nullable=True))
    op.add_column('embedding_runs', sa.Column('retrieval_chunk_count', sa.Integer(), nullable=True))

    # 3. passage_source_blocks: span provenance
    op.add_column(
        'passage_source_blocks',
        sa.Column('source_char_start', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'passage_source_blocks',
        sa.Column('source_char_end', sa.Integer(), nullable=False, server_default='0'),
    )
    op.execute(
        """
        UPDATE passage_source_blocks psb
        SET source_char_end = char_length(COALESCE(tb.cleaned_text, tb.raw_text))
        FROM text_blocks tb
        WHERE tb.id = psb.text_block_id
        """
    )
    op.alter_column('passage_source_blocks', 'source_char_start', server_default=None)
    op.alter_column('passage_source_blocks', 'source_char_end', server_default=None)
    op.drop_constraint(
        'uq_passage_source_blocks_run_text_block', 'passage_source_blocks', type_='unique'
    )
    op.create_unique_constraint(
        'uq_passage_source_blocks_run_text_block_span',
        'passage_source_blocks',
        ['segmentation_run_id', 'text_block_id', 'source_char_start'],
    )

    # 4. passage_alignments: semantic score provenance
    op.add_column('passage_alignments', sa.Column('semantic_similarity_basis', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('passage_alignments', 'semantic_similarity_basis')

    op.drop_constraint(
        'uq_passage_source_blocks_run_text_block_span', 'passage_source_blocks', type_='unique'
    )
    op.create_unique_constraint(
        'uq_passage_source_blocks_run_text_block', 'passage_source_blocks', ['segmentation_run_id', 'text_block_id']
    )
    op.drop_column('passage_source_blocks', 'source_char_end')
    op.drop_column('passage_source_blocks', 'source_char_start')

    op.drop_column('embedding_runs', 'retrieval_chunk_count')
    op.drop_column('embedding_runs', 'oversized_chunked_passage_count')

    op.drop_index('ix_passage_retrieval_chunks_embedding_hnsw_cosine', table_name='passage_retrieval_chunks')
    op.drop_index('ix_passage_retrieval_chunks_embedding_run_id', table_name='passage_retrieval_chunks')
    op.drop_index('ix_passage_retrieval_chunks_passage_id', table_name='passage_retrieval_chunks')
    op.drop_table('passage_retrieval_chunks')
