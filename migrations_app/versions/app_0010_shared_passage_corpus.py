"""shared publication-independent passage corpus (Track 7E.1)

Revision ID: app_0010
Revises: app_0009
Create Date: 2026-09-17 00:00:00.000000

Track 7E.1 storage/lifecycle hardening: `app.passages`/`app.passage_
embeddings` physically duplicate every unchanged passage's text and
embedding vector on every single publish -- verified locally (docs/7e1-
publication-storage-lifecycle-hardening.md section 2) to be 100% byte-for-
byte identical across two publications built from unchanged source data.
`passage_embeddings` alone measured 143MB in production for one publication.

Adds `app_corpus.passages`/`app_corpus.passage_embeddings`: two tables NOT
scoped by `publication_id`, holding exactly one physical copy of each
distinct passage's text (by `source_passage_id`) and each distinct
embedding vector (by `source_passage_id` + embedding model/revision), no
matter how many publications reference it. IDs are deterministic via
`labels.derive_corpus_id` (same `derive_id` scheme, with `publication_
version` fixed to the reserved `labels.CORPUS_SCOPE` sentinel), so two
publishes of the same unchanged passage always resolve to the same corpus
row instead of writing a second one.

This is an ADDITIVE, backward-compatible migration (7E.1 section 9 -- no
destructive conversion in one migration):

  * `app.passages.text` becomes nullable. Existing rows keep their
    populated value untouched -- nothing is backfilled to NULL. The
    publisher leaves it NULL for every new publish from this migration
    onward; `app.current_passages` resolves the real text via `COALESCE`
    against a join to `app_corpus.passages`, so old and new publications
    both read correctly through the same view.
  * The FK from `app.retrieval_contexts.passage_embedding_id` to
    `app.passage_embeddings.id` is dropped (not replaced by a new FK to
    `app_corpus.passage_embeddings` -- a single column cannot enforce two
    different targets for old vs. new rows). Cross-referential integrity is
    checked by `publishing.validation` instead, exactly like the existing
    `Company.latest_comparison_id` pattern. See that column's docstring in
    `models.py`.
  * `app.passage_embeddings` itself is NOT altered or emptied -- existing
    per-publication rows for already-built publications are left exactly as
    they are (harmless; they stop growing, they are not rewritten). The
    publisher simply stops inserting into this table from this migration
    onward.
  * Existing `app.passages`/`app.passage_embeddings` content is backfilled
    into the two new corpus tables (deduplicated via `ON CONFLICT DO
    NOTHING` against the natural unique key) so `app.current_passages`/
    `app.current_passage_embeddings` resolve correctly for publications
    built *before* this migration too -- no publication loses data, no
    publication needs rebuilding to keep working.

`current_passages`/`current_passage_embeddings` are redefined in their own
`CORPUS_CURRENT_VIEWS` tuple (`market_documents.publishing.schema`),
executed only here -- same migration-replay-safety reasoning documented on
`RETRIEVAL_CURRENT_VIEWS`/`QA_CHUNK_CURRENT_VIEWS`/
`CUTOVER_COMPARISON_CURRENT_VIEWS`.

See docs/7e1-publication-storage-lifecycle-hardening.md for the full audit,
the local two-publication storage measurement, and the production capacity
estimate.
"""
from typing import Sequence, Union
import uuid

from alembic import op
import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TSVECTOR

from market_documents.publishing import labels
from market_documents.publishing.schema import CORPUS_CURRENT_VIEWS, CREATE_CORPUS_SCHEMA_SQL

# revision identifiers, used by Alembic.
revision: str = 'app_0010'
down_revision: Union[str, Sequence[str], None] = 'app_0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BACKFILL_BATCH_SIZE = 500


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(CREATE_CORPUS_SCHEMA_SQL)

    op.create_table(
        'passages',
        sa.Column('source_passage_id', sa.UUID(), nullable=False),
        sa.Column('heading', sa.Text(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column(
            'search_vector',
            TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('pg_catalog.english', coalesce(heading, '')), 'A') || "
                "setweight(to_tsvector('pg_catalog.english', text), 'B')",
                persisted=True,
            ),
            nullable=True,
        ),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_passage_id', name='uq_app_corpus_passages_source'),
        schema='app_corpus',
    )
    op.create_index(
        'ix_app_corpus_passages_search_vector', 'passages', ['search_vector'],
        unique=False, schema='app_corpus', postgresql_using='gin',
    )

    op.create_table(
        'passage_embeddings',
        sa.Column('source_passage_id', sa.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_passage_id', 'embedding_model', 'embedding_model_revision',
            name='uq_app_corpus_passage_embeddings_scope',
        ),
        schema='app_corpus',
    )
    op.create_index(
        'ix_app_corpus_passage_embeddings_hnsw_cosine', 'passage_embeddings', ['embedding'],
        unique=False, schema='app_corpus', postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )

    # Relax NOT NULL -- new publishes leave this column NULL, existing rows
    # keep their value untouched.
    op.alter_column('passages', 'text', nullable=True, schema='app')

    # Drop the DB-level FK: a single column can no longer enforce one target
    # table now that new publications point at `app_corpus.passage_
    # embeddings` instead of `app.passage_embeddings`. See the column's
    # docstring in `models.py`.
    op.drop_constraint(
        'retrieval_contexts_passage_embedding_id_fkey', 'retrieval_contexts', schema='app', type_='foreignkey'
    )

    _backfill_corpus_tables()

    for _name, statement in CORPUS_CURRENT_VIEWS:
        op.execute(statement)


def _backfill_corpus_tables() -> None:
    """Idempotent: safe to re-run (e.g. against a partially-applied prior
    attempt) -- every insert is `ON CONFLICT DO NOTHING` against the natural
    unique key, and ids are deterministic, so a re-run never creates a
    duplicate or a second id for the same source content.

    Deliberately never pulls `text` or `embedding` values into Python: only
    the small identifying columns needed to compute each row's deterministic
    corpus id are fetched here, via a temp id-mapping table joined back in a
    single server-side `INSERT ... SELECT` -- the heavy payload moves
    Postgres-to-Postgres, never round-tripping through the migration
    process (and never risking a vector-literal (de)serialization mismatch
    between the raw DB-API connection Alembic uses here and the app's
    pgvector-registered connections elsewhere)."""
    bind = op.get_bind()

    passage_ids = bind.execute(
        sa.text("SELECT DISTINCT source_passage_id FROM app.passages WHERE text IS NOT NULL")
    ).fetchall()
    _backfill_via_mapping(
        bind,
        mapping=[
            (str(row.source_passage_id), labels.derive_corpus_id("passages", str(row.source_passage_id)))
            for row in passage_ids
        ],
        insert_sql=(
            "INSERT INTO app_corpus.passages (id, source_passage_id, heading, text) "
            "SELECT DISTINCT ON (t.source_passage_id) m.new_id, t.source_passage_id, t.heading, t.text "
            "FROM app.passages t "
            "JOIN pg_temp.corpus_id_map m ON m.source_passage_id = t.source_passage_id::text "
            "WHERE t.text IS NOT NULL "
            "ORDER BY t.source_passage_id, t.created_at DESC "
            "ON CONFLICT (source_passage_id) DO NOTHING"
        ),
    )

    embedding_keys = bind.execute(
        sa.text(
            "SELECT DISTINCT p.source_passage_id, pe.embedding_model, pe.embedding_model_revision "
            "FROM app.passage_embeddings pe JOIN app.passages p ON p.id = pe.passage_id"
        )
    ).fetchall()
    _backfill_via_mapping(
        bind,
        mapping=[
            (
                f"{row.source_passage_id}:{row.embedding_model}:{row.embedding_model_revision}",
                labels.derive_corpus_id(
                    "passage_embeddings", str(row.source_passage_id), row.embedding_model, row.embedding_model_revision
                ),
            )
            for row in embedding_keys
        ],
        insert_sql=(
            "INSERT INTO app_corpus.passage_embeddings "
            "(id, source_passage_id, source_embedding_id, source_embedding_run_id, embedding_model, "
            "embedding_model_revision, dimensions, embedding_text_hash, embedding, vector_norm) "
            "SELECT DISTINCT ON (p.source_passage_id, pe.embedding_model, pe.embedding_model_revision) "
            "m.new_id, p.source_passage_id, pe.source_embedding_id, pe.source_embedding_run_id, "
            "pe.embedding_model, pe.embedding_model_revision, pe.dimensions, pe.embedding_text_hash, "
            "pe.embedding, pe.vector_norm "
            "FROM app.passage_embeddings pe "
            "JOIN app.passages p ON p.id = pe.passage_id "
            "JOIN pg_temp.corpus_id_map m "
            "  ON m.source_passage_id = (p.source_passage_id::text || ':' || pe.embedding_model || ':' || pe.embedding_model_revision) "
            "ORDER BY p.source_passage_id, pe.embedding_model, pe.embedding_model_revision, pe.created_at DESC "
            "ON CONFLICT (source_passage_id, embedding_model, embedding_model_revision) DO NOTHING"
        ),
    )


def _backfill_via_mapping(bind, *, mapping: list[tuple[str, uuid.UUID]], insert_sql: str) -> None:
    if not mapping:
        return
    bind.execute(sa.text("CREATE TEMP TABLE corpus_id_map (source_passage_id text PRIMARY KEY, new_id uuid NOT NULL) ON COMMIT DROP"))
    for start in range(0, len(mapping), _BACKFILL_BATCH_SIZE):
        batch = mapping[start : start + _BACKFILL_BATCH_SIZE]
        bind.execute(
            sa.text("INSERT INTO corpus_id_map (source_passage_id, new_id) VALUES (:key, :new_id)"),
            [{"key": key, "new_id": new_id} for key, new_id in batch],
        )
    bind.execute(sa.text(insert_sql))
    bind.execute(sa.text("DROP TABLE corpus_id_map"))


def downgrade() -> None:
    """Downgrade schema."""
    for name, _ in reversed(CORPUS_CURRENT_VIEWS):
        op.execute(f"DROP VIEW IF EXISTS app.{name};")

    # Restore the pre-7E.1 views so `current_passages`/`current_passage_
    # embeddings` keep working against `app.passages`/`app.passage_
    # embeddings` alone (the only tables a downgraded schema still trusts).
    from market_documents.publishing.schema import CURRENT_VIEWS, RETRIEVAL_CURRENT_VIEWS

    for name, statement in CURRENT_VIEWS:
        if name in ("current_passages",):
            op.execute(statement)
    for name, statement in RETRIEVAL_CURRENT_VIEWS:
        if name in ("current_passage_embeddings",):
            op.execute(statement)

    op.create_foreign_key(
        'retrieval_contexts_passage_embedding_id_fkey', 'retrieval_contexts', 'passage_embeddings',
        ['passage_embedding_id'], ['id'], source_schema='app', referent_schema='app', ondelete='CASCADE',
    )
    op.alter_column('passages', 'text', nullable=False, schema='app')

    op.drop_index(
        'ix_app_corpus_passage_embeddings_hnsw_cosine', table_name='passage_embeddings', schema='app_corpus',
        postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.drop_table('passage_embeddings', schema='app_corpus')
    op.drop_index('ix_app_corpus_passages_search_vector', table_name='passages', schema='app_corpus')
    op.drop_table('passages', schema='app_corpus')
