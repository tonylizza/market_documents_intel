"""Embedding-service runtime configuration -- deployment knobs only (timeouts,
network binding). Model/analysis configuration is never duplicated here; it
always comes straight from `services.embedding_config`.
"""

import os
from dataclasses import dataclass

PROVIDER_IDENTIFIER = "local-python-fastapi"


@dataclass(frozen=True)
class EmbeddingServiceSettings:
    request_timeout_seconds: float = 10.0
    host: str = "0.0.0.0"
    port: int = 8081


def get_embedding_service_settings() -> EmbeddingServiceSettings:
    return EmbeddingServiceSettings(
        request_timeout_seconds=float(os.environ.get("EMBEDDING_SERVICE_TIMEOUT_SECONDS", "10.0")),
        host=os.environ.get("EMBEDDING_SERVICE_HOST", "0.0.0.0"),
        port=int(os.environ.get("EMBEDDING_SERVICE_PORT", "8081")),
    )
