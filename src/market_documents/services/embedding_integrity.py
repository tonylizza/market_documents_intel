"""Embedding vector integrity checks against the real (or fixture) corpus.

Dimension, NaN, and Infinity are already rejected by the `vector(384)`
column type itself at insert time -- pgvector's `vector_in` refuses NaN and
Infinity outright, and the column's fixed dimension is part of the type
(see `test_vector_dimension_is_enforced`, `test_nan_embedding_is_rejected`,
`test_infinite_embedding_is_rejected`). A zero vector, however, is a valid
pgvector value (`vector_norm` = 0) that Postgres will happily store, and its
cosine distance to anything is undefined (division by zero magnitude) --
this module exists to catch that case explicitly, since nothing else would.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class EmbeddingIntegrityReport:
    total_vectors: int
    zero_vector_count: int
    zero_vector_passage_ids: list[str]

    @property
    def is_clean(self) -> bool:
        return self.zero_vector_count == 0


def check_embedding_integrity(session: Session) -> EmbeddingIntegrityReport:
    total = session.execute(text("SELECT count(*) FROM passage_embeddings")).scalar_one()
    zero_rows = session.execute(
        text("SELECT passage_id FROM passage_embeddings WHERE vector_norm(embedding) = 0")
    ).all()
    return EmbeddingIntegrityReport(
        total_vectors=total,
        zero_vector_count=len(zero_rows),
        zero_vector_passage_ids=[str(row[0]) for row in zero_rows],
    )
