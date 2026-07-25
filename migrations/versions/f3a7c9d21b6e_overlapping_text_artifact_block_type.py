"""overlapping text artifact block type

Revision ID: f3a7c9d21b6e
Revises: 2ee4738d0d76
Create Date: 2026-07-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a7c9d21b6e'
down_revision: Union[str, Sequence[str], None] = '2ee4738d0d76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add BlockType.OVERLAPPING_TEXT_ARTIFACT for the geometric-density
    corruption detector (overlapping/duplicated decorative text objects,
    e.g. cover-page wordmark effects) added to block_classification."""
    op.execute("ALTER TYPE block_type ADD VALUE 'OVERLAPPING_TEXT_ARTIFACT'")


def downgrade() -> None:
    """PostgreSQL cannot drop a single enum value in place, so rebuild
    block_type without it: rename the old type aside, recreate it with the
    original value set, and cast the column across. The USING cast fails
    loudly (transaction rolled back, nothing partially applied) if any
    text_blocks row still holds 'OVERLAPPING_TEXT_ARTIFACT' -- correct,
    since that data would otherwise be silently destroyed.
    """
    op.execute("ALTER TYPE block_type RENAME TO block_type_old")
    op.execute(
        "CREATE TYPE block_type AS ENUM ("
        "'PARAGRAPH', 'HEADING_CANDIDATE', 'LIST_ITEM', 'TABLE_LIKE', 'HEADER', "
        "'FOOTER', 'PAGE_NUMBER', 'NUMERIC_FRAGMENT', 'DECORATIVE_OR_FRAGMENT', 'UNKNOWN'"
        ")"
    )
    op.execute(
        "ALTER TABLE text_blocks ALTER COLUMN block_type TYPE block_type "
        "USING block_type::text::block_type"
    )
    op.execute("DROP TYPE block_type_old")
