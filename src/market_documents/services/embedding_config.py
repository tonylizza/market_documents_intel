"""Centralized, versioned embedding-model configuration and reproducibility pins.

Mirrors `extraction_config.py`/`similarity_config.py`/`passage_config.py`:
these are analysis parameters, not per-deployment settings.

Model selection: BAAI/bge-small-en-v1.5 (MIT license), a compact
sentence-transformers model that runs on CPU. Verified directly against its
Hugging Face model card and repository metadata:

- License: MIT, free for commercial use.
- 384-dimensional output, 512 max input tokens, 33.4M parameters.
- Pooling: CLS token (see `1_Pooling/config.json` in the pinned revision).
- The model's own pipeline includes a `2_Normalize` module (see
  `modules.json`), so output vectors are already unit-L2-normalized;
  `normalize_embeddings=True` is still passed explicitly at encode time as a
  documented, non-silent guarantee rather than relying on that implicitly.
- No input prefix is applied to any passage. BGE v1.5 only recommends an
  optional query-side instruction for asymmetric retrieval and works well
  without it; e5-small-v2 (the other compact candidate) *requires*
  "query: "/"passage: " prefixes, which would force two different embeddings
  per passage since a report's passages are "later" (query-like) in one
  ReportPair and can be "earlier" (corpus-like) in the next pair for the
  same company -- BGE's prefix-free design avoids that role-dependent
  duplication entirely.
- `MODEL_REVISION` is the exact commit SHA resolved via
  `huggingface_hub.HfApi().model_info("BAAI/bge-small-en-v1.5").sha` at the
  time this model was approved, not the mutable "main" branch name.
"""

import hashlib
import importlib.metadata
import json
from dataclasses import asdict, dataclass

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
TOKENIZER_NAME = MODEL_NAME
TOKENIZER_REVISION = MODEL_REVISION

EMBEDDING_DIMENSION = 384
POOLING_STRATEGY = "cls"
NORMALIZATION_METHOD = "l2"
MAXIMUM_MODEL_TOKENS = 512
# No prefix applied to any passage -- see module docstring.
INPUT_PREFIX: str | None = None

EMBEDDING_CONFIG_VERSION = 1


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str = MODEL_NAME
    model_revision: str = MODEL_REVISION
    tokenizer_name: str = TOKENIZER_NAME
    tokenizer_revision: str = TOKENIZER_REVISION
    embedding_dimension: int = EMBEDDING_DIMENSION
    pooling_strategy: str = POOLING_STRATEGY
    normalization_method: str = NORMALIZATION_METHOD
    maximum_model_tokens: int = MAXIMUM_MODEL_TOKENS
    input_prefix: str | None = INPUT_PREFIX
    batch_size: int = 32


EMBEDDING_CONFIG = EmbeddingConfig()


def _sentence_transformers_version() -> str:
    try:
        return importlib.metadata.version("sentence-transformers")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _transformers_version() -> str:
    try:
        return importlib.metadata.version("transformers")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def compute_configuration_hash(config: EmbeddingConfig = EMBEDDING_CONFIG) -> str:
    """Deterministic fingerprint of everything that can change embedding output.

    An identical fingerprint means: same model revision, same tokenizer
    revision, same pooling/normalization/prefix behavior, same library
    versions. Any change triggers a fresh `EmbeddingRun` instead of a skip.
    """
    payload = {
        "embedding_config_version": EMBEDDING_CONFIG_VERSION,
        "sentence_transformers_version": _sentence_transformers_version(),
        "transformers_version": _transformers_version(),
        "config": asdict(config),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
