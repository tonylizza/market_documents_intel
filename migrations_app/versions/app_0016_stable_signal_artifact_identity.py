"""stable signal-artifact identity + index-usable QA vector view (Track 7F.10)

Revision ID: app_0016
Revises: app_0015
Create Date: 2026-09-24 00:00:00.000000

1. `app_artifacts.passage_language_signals` identity moves from the
   transient research `PassageLanguageSignal.id` (`source_signal_id`) to the
   stable (`source_passage_alignment_id`, `report_side`, `category`,
   `subcategory`, `language_signal_artifact_version`) tuple, introduced
   together with `labels.LANGUAGE_SIGNAL_ARTIFACT_VERSION` = signals_v2.
   Existing signals_v1 rows are left exactly as they are (immutable; still
   referenced by any retained pre-7F.10 publication), so:

   - `source_signal_id` becomes nullable (NULL on signals_v2+ rows);
   - the old full unique constraint becomes a partial unique index scoped to
     `source_signal_id IS NOT NULL` (the v1 scheme, unchanged semantics);
   - a second partial unique index enforces the v2 scheme;
   - a CHECK guarantees every row carries one of the two identities.

   Nothing is backfilled: v1 rows cannot be re-keyed onto the v2 tuple,
   because a v1 generation can legitimately hold two rows for one
   (alignment, side, category, subcategory) -- exactly the 7F.9 duplication
   this track removes.

2. `ix_app_qa_chunks_artifact_publication` on `app.qa_chunks`
   (`qa_chunking_artifact_id`, `publication_id`): lets the artifact-first
   QA vector query drive an HNSW scan on `app_artifacts.qa_chunks` and
   resolve each candidate to the active publication's thin row with a
   nested-loop index lookup (the planner otherwise hash-joins and loses the
   index order).

3. `app.current_qa_chunk_vectors`: an index-usable current view for QA
   vector search (see `schema.QA_CHUNK_VECTOR_CURRENT_VIEWS`).
   `app.current_qa_chunks` is unchanged and still serves every relational
   and exact/company-scoped query.

IMPORTANT: follow this migration with `scripts/sql/app_grants.sql`, which
grants `app_readonly` SELECT on the new view. Until then the web tier's
HNSW path fails closed with permission denied.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from market_documents.publishing.schema import (
    DROP_QA_CHUNK_VECTOR_CURRENT_VIEWS_SQL,
    QA_CHUNK_VECTOR_CURRENT_VIEWS,
)

# revision identifiers, used by Alembic.
revision: str = 'app_0016'
down_revision: Union[str, Sequence[str], None] = 'app_0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SCHEMA = 'app_artifacts'
_TABLE = 'passage_language_signals'
_SCOPE_COLUMNS = ['report_side', 'category', 'subcategory', 'language_signal_artifact_version']


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column('source_passage_alignment_id', sa.UUID(), nullable=True), schema=_SCHEMA)
    op.add_column(_TABLE, sa.Column('source_passage_id', sa.UUID(), nullable=True), schema=_SCHEMA)
    op.alter_column(_TABLE, 'source_signal_id', existing_type=sa.UUID(), nullable=True, schema=_SCHEMA)

    op.drop_constraint('uq_app_artifacts_passage_language_signals_scope', _TABLE, schema=_SCHEMA, type_='unique')
    op.create_index(
        'uq_app_artifacts_passage_language_signals_scope', _TABLE, ['source_signal_id', *_SCOPE_COLUMNS],
        unique=True, schema=_SCHEMA, postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text('source_signal_id IS NOT NULL'),
    )
    op.create_index(
        'uq_app_artifacts_passage_language_signals_alignment_scope', _TABLE,
        ['source_passage_alignment_id', *_SCOPE_COLUMNS],
        unique=True, schema=_SCHEMA, postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text('source_passage_alignment_id IS NOT NULL'),
    )
    op.create_check_constraint(
        'ck_app_artifacts_passage_language_signals_identity', _TABLE,
        'source_signal_id IS NOT NULL OR source_passage_alignment_id IS NOT NULL', schema=_SCHEMA,
    )

    op.create_index(
        'ix_app_qa_chunks_artifact_publication', 'qa_chunks', ['qa_chunking_artifact_id', 'publication_id'],
        unique=False, schema='app',
    )
    for _name, statement in QA_CHUNK_VECTOR_CURRENT_VIEWS:
        op.execute(statement)


def downgrade() -> None:
    # Refuse rather than silently delete: a signals_v2+ row has no
    # `source_signal_id`, so it cannot satisfy app_0015's NOT NULL identity,
    # and deleting it would break every retained publication that references
    # it. Clean up those publications and run `publish gc-artifacts` first.
    bind = op.get_bind()
    v2_rows = bind.execute(
        sa.text(f'SELECT count(*) FROM {_SCHEMA}.{_TABLE} WHERE source_signal_id IS NULL')
    ).scalar_one()
    if v2_rows:
        raise RuntimeError(
            f'app_0016 downgrade refused: {v2_rows} app_artifacts.passage_language_signals rows use the '
            'signals_v2 alignment-keyed identity (source_signal_id IS NULL). Remove the publications that '
            'reference them and run `publish gc-artifacts` before downgrading.'
        )

    for statement in DROP_QA_CHUNK_VECTOR_CURRENT_VIEWS_SQL:
        op.execute(statement)
    op.drop_index('ix_app_qa_chunks_artifact_publication', table_name='qa_chunks', schema='app')

    op.drop_constraint('ck_app_artifacts_passage_language_signals_identity', _TABLE, schema=_SCHEMA, type_='check')
    op.drop_index('uq_app_artifacts_passage_language_signals_alignment_scope', table_name=_TABLE, schema=_SCHEMA)
    op.drop_index('uq_app_artifacts_passage_language_signals_scope', table_name=_TABLE, schema=_SCHEMA)
    op.create_unique_constraint(
        'uq_app_artifacts_passage_language_signals_scope', _TABLE, ['source_signal_id', *_SCOPE_COLUMNS],
        schema=_SCHEMA, postgresql_nulls_not_distinct=True,
    )
    op.alter_column(_TABLE, 'source_signal_id', existing_type=sa.UUID(), nullable=False, schema=_SCHEMA)
    op.drop_column(_TABLE, 'source_passage_id', schema=_SCHEMA)
    op.drop_column(_TABLE, 'source_passage_alignment_id', schema=_SCHEMA)
