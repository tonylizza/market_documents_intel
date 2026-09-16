"""rename lexical_unit_comparisons.lexical_cosine_similarity to tfidf_cosine

Track 7C.3 correction: the persisted "TF-IDF cosine" field was originally
computed with the document-pipeline's sublinear-TF `lexical_cosine_similarity`
(explicitly NOT TF-IDF) and named accordingly. It is now computed with a
genuine pairwise TF-IDF cosine
(`services.similarity_metrics.pairwise_tfidf_cosine_similarity`), matching
docs/experiments/annual-report-lexical-change-pilot.md's "TF-IDF cosine"
metric -- so the column is renamed to describe what it actually is.

Revision ID: 3ac7dda97887
Revises: 3b24f4904672
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '3ac7dda97887'
down_revision: Union[str, Sequence[str], None] = '3b24f4904672'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('lexical_unit_comparisons', 'lexical_cosine_similarity', new_column_name='tfidf_cosine')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('lexical_unit_comparisons', 'tfidf_cosine', new_column_name='lexical_cosine_similarity')
