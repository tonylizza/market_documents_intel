"""passage embedding hnsw index

Adds an approximate-nearest-neighbor index on `passage_embeddings.embedding`
for future unrestricted/whole-corpus search and dashboard workloads
(Milestone 7). Uses `vector_cosine_ops` to match the cosine distance
(`<=>`) operator already used by `alignment_candidates.get_semantic_candidates`.

Exact retrieval remains the default (see `retrieval_config.py`):
real-corpus benchmarking found no measurable recall or latency benefit for
the retrieval pattern actually in use today (single-`embedding_run_id`-
restricted candidate search over ~2,000-2,500 rows, already served in
single-digit milliseconds by the existing `embedding_run_id` B-tree). The
index is retained for later use, not switched on as the default.

Revision ID: 2ee4738d0d76
Revises: 2caf70d7f084
Create Date: 2026-07-24 13:23:46.657518

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ee4738d0d76'
down_revision: Union[str, Sequence[str], None] = '2caf70d7f084'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ix_passage_embeddings_embedding_hnsw_cosine",
        "passage_embeddings",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_passage_embeddings_embedding_hnsw_cosine", table_name="passage_embeddings")
