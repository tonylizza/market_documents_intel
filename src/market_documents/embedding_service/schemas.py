"""Request/response schemas for the query-embedding HTTP service.

Kept separate from the research `market_documents.schemas` package (which
describes CLI/report-shaped data): these are a small, narrow HTTP contract
for exactly three endpoints, never a general-purpose model-serving API.
"""

from pydantic import BaseModel, Field

# A generous but bounded ceiling -- well above any realistic search query,
# far below the point where tokenization/encoding cost becomes a DoS
# surface. Enforced before the text ever reaches the tokenizer.
MAXIMUM_QUERY_CHARACTERS = 2000


class EmbedQueryRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAXIMUM_QUERY_CHARACTERS)


class EmbedQueryResponse(BaseModel):
    vector: list[float]
    model: str
    model_revision: str
    dimensions: int
    normalized_text: str
    token_count: int
    latency_ms: float
    provider: str


class MetadataResponse(BaseModel):
    model: str
    model_revision: str
    tokenizer: str
    tokenizer_revision: str
    dimensions: int
    pooling_strategy: str
    normalization_method: str
    maximum_model_tokens: int
    input_prefix: str | None
    maximum_query_characters: int
    provider: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    detail: str | None = None
