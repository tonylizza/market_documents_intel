"""Centralized, versioned retrieval-subchunking configuration (Milestone 6).

Mirrors `embedding_config.py`/`passage_config.py`: these are analysis
parameters, not per-deployment settings. Unlike `retrieval_config.py`
(which only changes how existing vectors are *queried*, never re-embedded),
a change here changes what actually gets embedded for an oversized
passage -- so, unlike `retrieval_config.py`, this module's hash is folded
into `embedding_config.compute_configuration_hash`, forcing a fresh
`EmbeddingRun` whenever the chunking policy changes.

See `docs/oversized-passage-retrieval-subchunks-experiment.md` for the full
rationale. Summary:

- `max_tokens=480`: the read-only Milestone 5 simulation
  (`docs/embedding-eligibility-token-limit-diagnostic.md` Section 11/14)
  resolved all 767 then-unembedded passages into token-safe subchunks under
  this ceiling, with a max observed subchunk of 475 tokens -- a ~6% margin
  under the model's hard 512-token limit for boundary-splitter imprecision
  and any future formatting prefix, without materially increasing subchunk
  count over a tighter ceiling. Adopted here as-is rather than re-deriving a
  new number without new evidence.
- `overlap_sentences=0`: that same simulation resolved 100% of cases with no
  overlap. The accepted risk (a strongly identifying phrase split across a
  chunk boundary) is a documented residual limitation, not mitigated
  speculatively -- see Section 8 of the milestone brief.
"""

import hashlib
import json
from dataclasses import asdict, dataclass

RETRIEVAL_CHUNKING_VERSION = 1


@dataclass(frozen=True)
class RetrievalChunkConfig:
    # Safe token ceiling per subchunk, measured with the real embedding
    # model tokenizer (the same `count_tokens` used for the >512 skip
    # check), not a word count.
    max_tokens: int = 480
    # No overlap between consecutive subchunks -- see module docstring.
    overlap_sentences: int = 0


RETRIEVAL_CHUNK_CONFIG = RetrievalChunkConfig()


def compute_retrieval_chunk_configuration_hash(config: RetrievalChunkConfig = RETRIEVAL_CHUNK_CONFIG) -> dict:
    """Returns a plain payload (not a hash string) for `embedding_config.py`
    to fold into its own configuration hash -- this module intentionally has
    no standalone hash of its own, since a chunking-policy change is only
    ever meaningful as part of what triggers a fresh `EmbeddingRun`."""
    return {
        "retrieval_chunking_version": RETRIEVAL_CHUNKING_VERSION,
        "config": asdict(config),
    }


def _self_hash(config: RetrievalChunkConfig = RETRIEVAL_CHUNK_CONFIG) -> str:
    """Standalone hash, used only by this module's own tests."""
    canonical = json.dumps(compute_retrieval_chunk_configuration_hash(config), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
