"""Centralized, versioned vector-retrieval mode configuration.

Mirrors `alignment_config.py`/`embedding_config.py`: these are analysis
parameters, not per-deployment settings. Distinct from `EmbeddingConfig`
(embedding_config.py) on purpose -- search mode changes how existing vectors
are queried, never what the vectors themselves are, so it must never affect
`EmbeddingRun.configuration_hash` or trigger re-embedding.

`vector_search_mode` defaults to EXACT: real-corpus benchmarking (see
`retrieval_benchmark.py`) found the HNSW index gives no measurable recall or
latency benefit for the retrieval pattern this codebase actually uses
(single-`embedding_run_id`-restricted candidate search over ~2,000-2,500
rows, already served in single-digit milliseconds by the existing
`embedding_run_id` B-tree). The index is retained for future unrestricted
search/dashboard workloads (Milestone 7), not enabled by default here.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum

RETRIEVAL_CONFIG_VERSION = 1

# Recall@10 an indexed configuration must reach, against exact retrieval on
# the same corpus, before it may be considered for default use. Not met by
# the real-corpus benchmark at this corpus size (see retrieval_benchmark.py
# results) -- retained here as the explicit bar for any future revisit.
MINIMUM_INDEXED_RECALL_AT_10 = 0.95


class VectorSearchMode(str, Enum):
    EXACT = "EXACT"
    HNSW = "HNSW"


@dataclass(frozen=True)
class RetrievalConfig:
    vector_search_mode: VectorSearchMode = VectorSearchMode.EXACT
    candidate_limit: int = 50
    # Only consulted when vector_search_mode is HNSW; pgvector's per-query
    # `hnsw.ef_search` session parameter (higher = more accurate, slower).
    hnsw_ef_search: int = 40


RETRIEVAL_CONFIG = RetrievalConfig()


def compute_retrieval_configuration_hash(config: RetrievalConfig = RETRIEVAL_CONFIG) -> str:
    """Deterministic fingerprint of retrieval-mode settings, for benchmark/audit
    provenance only -- never combined with `EmbeddingConfig`'s hash, and never
    a factor in whether an embedding or alignment run is considered stale."""
    payload = {
        "retrieval_config_version": RETRIEVAL_CONFIG_VERSION,
        "config": asdict(config),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
