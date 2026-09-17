"""semantic unit source block canonical source

Track 7D.2a (docs/7d2a-semantic-unit-extraction-hardening.md):
`semantic_unit_extraction.py` now prefers the canonical PDF source
(Track 7C.1a) over legacy `TextBlock` when a report has a current
successful `CanonicalExtractionRun`, mirroring `schedule_localization.py`'s
own canonical preference (its 7C.1b). `SemanticUnitSourceBlock.text_block_id`
was a required, non-nullable FK to `text_blocks.id` -- it cannot record
provenance from a canonical run, whose blocks live in `canonical_blocks`,
a different table with different primary keys. Makes `text_block_id`
nullable and adds a nullable `canonical_block_id` FK to `canonical_blocks.id`
(ondelete CASCADE, indexed) alongside it, mirroring the same
canonical-block-FK pattern `structured_table.py` already uses (e.g.
`StructuredTableRow.canonical_block_id`). Exactly one of the two is set per
row, enforced in application code (`semantic_unit_extraction._run_extraction`),
not a database constraint -- consistent with how this codebase already
treats analogous either/or provenance columns.

Revision ID: a4c1e8f2b6d9
Revises: db8ee3ff6003
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c1e8f2b6d9'
down_revision: Union[str, Sequence[str], None] = 'db8ee3ff6003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('semantic_unit_source_blocks', 'text_block_id', existing_type=sa.UUID(), nullable=True)
    op.add_column('semantic_unit_source_blocks', sa.Column('canonical_block_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'semantic_unit_source_blocks_canonical_block_id_fkey',
        'semantic_unit_source_blocks', 'canonical_blocks',
        ['canonical_block_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index(
        'ix_semantic_unit_source_blocks_canonical_block_id',
        'semantic_unit_source_blocks', ['canonical_block_id'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_semantic_unit_source_blocks_canonical_block_id', table_name='semantic_unit_source_blocks')
    op.drop_constraint(
        'semantic_unit_source_blocks_canonical_block_id_fkey',
        'semantic_unit_source_blocks', type_='foreignkey',
    )
    op.drop_column('semantic_unit_source_blocks', 'canonical_block_id')
    op.alter_column('semantic_unit_source_blocks', 'text_block_id', existing_type=sa.UUID(), nullable=False)
