"""Milestone 7B.1: query-embedding HTTP service.

Uses a fake `EmbeddingModel` (same protocol the research pipeline's own
tests inject -- see `services/passage_embedding.py::EmbeddingModel`) so
these tests are fast, deterministic, and never require downloading or
running the real Hugging Face model.
"""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from market_documents.embedding_service import app as embedding_app_module
from market_documents.embedding_service.app import app
from market_documents.embedding_service.normalization import normalize_query_text
from market_documents.services.embedding_config import EMBEDDING_CONFIG
from market_documents.services.passage_embedding import EncodedPassage


class _FakeModel:
    def __init__(self, *, delay_seconds: float = 0.0, dimension: int = EMBEDDING_CONFIG.embedding_dimension):
        self.delay_seconds = delay_seconds
        self.dimension = dimension
        self.calls: list[str] = []

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def encode_batch(self, texts: list[str]) -> list[EncodedPassage]:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        self.calls.extend(texts)
        return [
            EncodedPassage(
                vector=[float(len(text) % 7)] * self.dimension, input_token_count=len(text.split()), truncated=False
            )
            for text in texts
        ]


@pytest.fixture(autouse=True)
def _reset_model_state():
    embedding_app_module._state.model = None
    embedding_app_module._state.load_error = None
    yield
    embedding_app_module._state.model = None
    embedding_app_module._state.load_error = None


@pytest.fixture
def client_with_fake_model():
    embedding_app_module._state.model = _FakeModel()
    return TestClient(app)


def test_health_ok_when_model_loaded(client_with_fake_model):
    response = client_with_fake_model.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": True, "detail": None}


def test_health_unavailable_when_model_fails_to_load(monkeypatch):
    def _raise():
        raise RuntimeError("no cached model and offline")

    monkeypatch.setattr(embedding_app_module, "get_embedding_model", _raise)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["model_loaded"] is False
    assert "no cached model" in body["detail"]


def test_metadata_returns_model_config(client_with_fake_model):
    response = client_with_fake_model.get("/metadata")
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == EMBEDDING_CONFIG.model_name
    assert body["model_revision"] == EMBEDDING_CONFIG.model_revision
    assert body["dimensions"] == EMBEDDING_CONFIG.embedding_dimension
    assert body["input_prefix"] is None
    assert body["provider"] == "local-python-fastapi"


def test_embed_query_returns_correct_dimension(client_with_fake_model):
    response = client_with_fake_model.post("/embed-query", json={"text": "liquidity risk disclosure"})
    assert response.status_code == 200
    body = response.json()
    assert len(body["vector"]) == EMBEDDING_CONFIG.embedding_dimension
    assert body["dimensions"] == EMBEDDING_CONFIG.embedding_dimension
    assert body["model"] == EMBEDDING_CONFIG.model_name
    assert body["provider"] == "local-python-fastapi"
    assert body["latency_ms"] >= 0


def test_embed_query_normalizes_whitespace(client_with_fake_model):
    response = client_with_fake_model.post("/embed-query", json={"text": "  liquidity   risk  \n disclosure "})
    assert response.status_code == 200
    assert response.json()["normalized_text"] == "liquidity risk disclosure"


def test_normalize_query_text_collapses_whitespace():
    assert normalize_query_text("  a   b\n\tc ") == "a b c"


def test_embed_query_deterministic_for_same_input(client_with_fake_model):
    first = client_with_fake_model.post("/embed-query", json={"text": "governance oversight"})
    second = client_with_fake_model.post("/embed-query", json={"text": "governance oversight"})
    assert first.json()["vector"] == second.json()["vector"]


def test_embed_query_rejects_empty_text(client_with_fake_model):
    response = client_with_fake_model.post("/embed-query", json={"text": ""})
    assert response.status_code == 422


def test_embed_query_rejects_missing_text_field(client_with_fake_model):
    response = client_with_fake_model.post("/embed-query", json={})
    assert response.status_code == 422


def test_embed_query_rejects_text_over_maximum_length(client_with_fake_model):
    response = client_with_fake_model.post("/embed-query", json={"text": "a" * 2001})
    assert response.status_code == 422


def test_embed_query_rejects_text_over_maximum_token_count():
    embedding_app_module._state.model = _FakeModel()
    client = TestClient(app)
    # Single-character "words" so the fake tokenizer's word-count token
    # estimate exceeds the model's token limit while staying well under the
    # character-length cap -- the two limits are independent checks, and
    # real English text almost always trips the character cap first, but
    # this exercises the token-count path in isolation.
    long_query = " ".join(["a"] * (EMBEDDING_CONFIG.maximum_model_tokens + 1))
    response = client.post("/embed-query", json={"text": long_query})
    assert response.status_code == 400
    assert "exceeds model limit" in response.json()["detail"]


def test_embed_query_times_out_on_slow_model(monkeypatch):
    from dataclasses import replace

    embedding_app_module._state.model = _FakeModel(delay_seconds=0.5)
    monkeypatch.setattr(
        embedding_app_module, "_settings", replace(embedding_app_module._settings, request_timeout_seconds=0.05)
    )
    client = TestClient(app)
    response = client.post("/embed-query", json={"text": "slow query"})
    assert response.status_code == 504


def test_embed_query_returns_503_when_model_unavailable(monkeypatch):
    monkeypatch.setattr(
        embedding_app_module,
        "get_embedding_model",
        lambda: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    client = TestClient(app)
    response = client.post("/embed-query", json={"text": "anything"})
    assert response.status_code == 503


def test_embed_query_dimension_mismatch_fails_clearly(client_with_fake_model):
    embedding_app_module._state.model = _FakeModel(dimension=128)
    client = TestClient(app)
    response = client.post("/embed-query", json={"text": "wrong dimension model"})
    assert response.status_code == 500
    assert "!=" in response.json()["detail"]


def test_no_corpus_or_admin_routes_exposed():
    route_paths = {route.path for route in app.routes}
    assert route_paths == {"/health", "/metadata", "/embed-query", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
