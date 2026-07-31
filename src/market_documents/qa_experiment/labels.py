"""Deterministic-ID scheme for the Milestone 7B.1d Q&A retrieval-chunk
experiment. Mirrors `publishing/labels.py::derive_id` exactly, but with its
own namespace so experiment ids can never collide with real publication ids,
and keyed by chunk *content* rather than by source row, so identical chunk
text (same publication_version + strategy) always resolves to the same id --
this is what makes cross-anchor deduplication free (see
`chunk_dedup.deduplicate`)."""

import uuid

# Frozen once computed: uuid.uuid5(uuid.NAMESPACE_URL,
# "https://qa-experiment.marketdocuments.internal/7b.1d"). Deliberately
# distinct from `publishing.labels.APP_ID_NAMESPACE`.
QA_EXPERIMENT_ID_NAMESPACE = uuid.UUID("6f2c6e0a-2f0e-5a3e-9c9f-6e6d3f0c9b21")


def derive_chunk_id(publication_version: str, chunk_strategy: str, text_hash: str) -> uuid.UUID:
    """Deterministic id for one chunk, keyed by its own text content.

    Two different anchor passages that happen to produce byte-identical
    chunk text (same strategy, same publication_version) resolve to the same
    chunk id -- deduplication is a natural consequence of this scheme, not a
    separate lookup table.
    """
    name = ":".join((publication_version, chunk_strategy, text_hash))
    return uuid.uuid5(QA_EXPERIMENT_ID_NAMESPACE, name)
