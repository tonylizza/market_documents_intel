"""table header fragment block type

Revision ID: b6e2f19a7c4d
Revises: 18e705b62fee
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b6e2f19a7c4d'
down_revision: Union[str, Sequence[str], None] = '18e705b62fee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add BlockType.TABLE_HEADER_FRAGMENT for the table-adjacency
    second-pass reclassification added to extraction (see
    services/block_classification.py::find_table_header_fragment_indices
    and docs/table-fragment-hardening-experiment.md). A HEADING_CANDIDATE
    block that is geometrically narrow and clustered with other narrow
    heading candidates near TABLE_LIKE content is reclassified to this type
    instead of surviving as a standalone heading-only passage."""
    op.execute("ALTER TYPE block_type ADD VALUE 'TABLE_HEADER_FRAGMENT'")


def downgrade() -> None:
    """PostgreSQL cannot drop a single enum value in place, so rebuild
    block_type without it: rename the old type aside, recreate it with the
    original value set, and cast the column across. The USING cast fails
    loudly (transaction rolled back, nothing partially applied) if any
    text_blocks row still holds 'TABLE_HEADER_FRAGMENT' -- correct, since
    that data would otherwise be silently destroyed.
    """
    op.execute("ALTER TYPE block_type RENAME TO block_type_old")
    op.execute(
        "CREATE TYPE block_type AS ENUM ("
        "'PARAGRAPH', 'HEADING_CANDIDATE', 'LIST_ITEM', 'TABLE_LIKE', 'HEADER', "
        "'FOOTER', 'PAGE_NUMBER', 'NUMERIC_FRAGMENT', 'DECORATIVE_OR_FRAGMENT', "
        "'OVERLAPPING_TEXT_ARTIFACT', 'UNKNOWN'"
        ")"
    )
    op.execute(
        "ALTER TABLE text_blocks ALTER COLUMN block_type TYPE block_type "
        "USING block_type::text::block_type"
    )
    op.execute("DROP TYPE block_type_old")
