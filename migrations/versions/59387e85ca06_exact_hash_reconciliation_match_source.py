"""exact hash reconciliation match source

Revision ID: 59387e85ca06
Revises: b6e2f19a7c4d
Create Date: 2026-09-09 16:09:24.618718

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59387e85ca06'
down_revision: Union[str, Sequence[str], None] = 'b6e2f19a7c4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add PassageAlignment.match_source, backfilling every pre-existing row
    (all produced by the primary matcher, before Milestone 2's exact-hash
    reconciliation post-pass existed) to 'PRIMARY' via server_default -- an
    accurate label for historical rows, not a change to any alignment
    result. See services/alignment_reconciliation.py and
    docs/exact-hash-reconciliation-experiment.md.

    Deliberately does not touch ix_passage_embeddings_embedding_hnsw_cosine
    -- autogenerate detected it as a diff (index exists in the DB but not in
    the model metadata) but that is pre-existing drift unrelated to this
    migration's scope, not something this revision should alter.
    """
    match_source = sa.Enum(
        'PRIMARY', 'EXACT_HASH_RECONCILIATION_UNIQUE', 'EXACT_HASH_RECONCILIATION_DUPLICATE_CLUSTER',
        name='alignment_match_source',
    )
    match_source.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'passage_alignments',
        sa.Column('match_source', match_source, nullable=False, server_default='PRIMARY'),
    )


def downgrade() -> None:
    op.drop_column('passage_alignments', 'match_source')
    sa.Enum(name='alignment_match_source').drop(op.get_bind(), checkfirst=True)
