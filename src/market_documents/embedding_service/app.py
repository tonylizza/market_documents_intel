"""Narrow query-embedding HTTP service (Milestone 7B.1).

Exposes exactly three endpoints -- `/health`, `/metadata`, `/embed-query` --
and nothing else: no corpus data, no arbitrary model selection, no generic
vector-query execution. Reuses the research pipeline's own model-loading and
encoding code (`services.passage_embedding.get_embedding_model`,
`SentenceTransformerEmbeddingModel`) rather than duplicating embedding
semantics, so a query vector is guaranteed comparable to the stored corpus
vectors (same model, same revision, same normalization, same no-prefix
convention -- see `services/embedding_config.py`).

Run locally with:
    .venv/bin/uvicorn market_documents.embedding_service.app:app --port 8081

The public Next.js application must call this service server-side only --
see the query-embedding provider in `web/lib/services/embedding-provider.ts`.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from starlette.concurrency import run_in_threadpool

from market_documents.embedding_service.config import PROVIDER_IDENTIFIER, get_embedding_service_settings
from market_documents.embedding_service.normalization import normalize_query_text
from market_documents.embedding_service.schemas import (
    EmbedQueryRequest,
    EmbedQueryResponse,
    HealthResponse,
    MetadataResponse,
)
from market_documents.services.embedding_config import EMBEDDING_CONFIG
from market_documents.services.passage_embedding import SentenceTransformerEmbeddingModel, get_embedding_model

logger = logging.getLogger(__name__)

_settings = get_embedding_service_settings()


class _ModelState:
    """Process-wide holder for the loaded model (or the reason it isn't
    loaded yet) -- separate from `get_embedding_model`'s own `lru_cache` so
    the service can report *why* it's unhealthy instead of just raising."""

    model: SentenceTransformerEmbeddingModel | None = None
    load_error: str | None = None


_state = _ModelState()


def _try_load_model() -> None:
    if _state.model is not None:
        return
    try:
        _state.model = get_embedding_model()
        _state.load_error = None
    except Exception as exc:  # noqa: BLE001 -- startup failure must be reported, not crash the process
        _state.load_error = str(exc)
        logger.exception("embedding model failed to load")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Best-effort at startup -- a slow/unavailable Hugging Face cache must
    # not prevent the process from starting; `/health` reports the real
    # state, and `/embed-query` retries the load on each request until it
    # succeeds once (after which `get_embedding_model`'s cache makes every
    # further call free).
    _try_load_model()
    yield


app = FastAPI(title="Query Embedding Service", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if _state.model is not None:
        return HealthResponse(status="ok", model_loaded=True)
    _try_load_model()
    if _state.model is not None:
        return HealthResponse(status="ok", model_loaded=True)
    return HealthResponse(status="unavailable", model_loaded=False, detail=_state.load_error)


@app.get("/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    return MetadataResponse(
        model=EMBEDDING_CONFIG.model_name,
        model_revision=EMBEDDING_CONFIG.model_revision,
        tokenizer=EMBEDDING_CONFIG.tokenizer_name,
        tokenizer_revision=EMBEDDING_CONFIG.tokenizer_revision,
        dimensions=EMBEDDING_CONFIG.embedding_dimension,
        pooling_strategy=EMBEDDING_CONFIG.pooling_strategy,
        normalization_method=EMBEDDING_CONFIG.normalization_method,
        maximum_model_tokens=EMBEDDING_CONFIG.maximum_model_tokens,
        input_prefix=EMBEDDING_CONFIG.input_prefix,
        maximum_query_characters=2000,
        provider=PROVIDER_IDENTIFIER,
    )


@app.post("/embed-query", response_model=EmbedQueryResponse)
async def embed_query(request: EmbedQueryRequest) -> EmbedQueryResponse:
    _try_load_model()
    if _state.model is None:
        raise HTTPException(status_code=503, detail=f"embedding model unavailable: {_state.load_error}")

    normalized = normalize_query_text(request.text)
    if not normalized:
        raise HTTPException(status_code=400, detail="query text is empty after normalization")

    model = _state.model
    token_count = model.count_tokens(normalized)
    if token_count > EMBEDDING_CONFIG.maximum_model_tokens:
        # A query is a live user request, not a batch passage -- unlike
        # research-side passage embedding (which skips an over-limit
        # passage rather than truncating it), there is no "skip" option for
        # a single live query. Fail clearly instead of silently truncating,
        # which would otherwise embed only part of what the user typed.
        raise HTTPException(
            status_code=400,
            detail=(
                f"query token count {token_count} exceeds model limit "
                f"({EMBEDDING_CONFIG.maximum_model_tokens}); shorten the query"
            ),
        )

    start = time.perf_counter()
    try:
        encoded = await asyncio.wait_for(
            run_in_threadpool(model.encode_batch, [normalized]),
            timeout=_settings.request_timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="embedding request timed out") from exc
    latency_ms = (time.perf_counter() - start) * 1000

    vector = encoded[0].vector
    if len(vector) != EMBEDDING_CONFIG.embedding_dimension:
        # Would indicate a model/config mismatch at runtime -- fail loudly
        # rather than return a vector the caller cannot safely compare
        # against the stored corpus vectors.
        raise HTTPException(
            status_code=500,
            detail=(
                f"encoded dimension {len(vector)} != configured dimension "
                f"{EMBEDDING_CONFIG.embedding_dimension}"
            ),
        )

    return EmbedQueryResponse(
        vector=vector,
        model=EMBEDDING_CONFIG.model_name,
        model_revision=EMBEDDING_CONFIG.model_revision,
        dimensions=len(vector),
        normalized_text=normalized,
        token_count=token_count,
        latency_ms=latency_ms,
        provider=PROVIDER_IDENTIFIER,
    )
