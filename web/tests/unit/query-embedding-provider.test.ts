import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CachingQueryEmbeddingProvider,
  HttpQueryEmbeddingProvider,
  QueryEmbeddingModelMismatchError,
  QueryEmbeddingProviderError,
  queryEmbeddingCacheKeyPrefix,
} from "@/lib/services/query-embedding-provider";

const CONFIG = {
  serviceUrl: "http://localhost:8081",
  timeoutMs: 5000,
  expectedModel: "BAAI/bge-small-en-v1.5",
  expectedModelRevision: "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
  expectedDimensions: 384,
};

function mockFetchOnce(response: unknown, ok = true, status = 200) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => response,
  }) as unknown as typeof fetch;
}

function validBody(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    vector: new Array(384).fill(0.1),
    model: CONFIG.expectedModel,
    model_revision: CONFIG.expectedModelRevision,
    dimensions: 384,
    normalized_text: "liquidity risk",
    token_count: 2,
    latency_ms: 12.5,
    provider: "local-python-fastapi",
    ...overrides,
  };
}

describe("HttpQueryEmbeddingProvider", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a validated QueryEmbedding on success", async () => {
    mockFetchOnce(validBody());
    const provider = new HttpQueryEmbeddingProvider(CONFIG);
    const result = await provider.embedQuery("liquidity risk");
    expect(result.vector).toHaveLength(384);
    expect(result.model).toBe(CONFIG.expectedModel);
    expect(result.provider).toBe("local-python-fastapi");
  });

  it("throws QueryEmbeddingModelMismatchError on model mismatch", async () => {
    mockFetchOnce(validBody({ model: "some-other-model" }));
    const provider = new HttpQueryEmbeddingProvider(CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingModelMismatchError);
  });

  it("throws QueryEmbeddingModelMismatchError on dimension mismatch", async () => {
    mockFetchOnce(validBody({ dimensions: 128, vector: new Array(128).fill(0.1) }));
    const provider = new HttpQueryEmbeddingProvider(CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingModelMismatchError);
  });

  it("throws QueryEmbeddingProviderError when the service responds with an error status", async () => {
    mockFetchOnce({ detail: "query too long" }, false, 400);
    const provider = new HttpQueryEmbeddingProvider(CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingProviderError);
  });

  it("throws QueryEmbeddingProviderError when fetch itself fails (service unreachable)", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("ECONNREFUSED")) as unknown as typeof fetch;
    const provider = new HttpQueryEmbeddingProvider(CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingProviderError);
  });
});

describe("CachingQueryEmbeddingProvider", () => {
  beforeEach(() => {
    (globalThis as { __queryEmbeddingCache?: Map<string, unknown> }).__queryEmbeddingCache = undefined;
  });

  it("calls the inner provider once and caches on the second identical call", async () => {
    const embedQuery = vi.fn().mockResolvedValue({
      vector: [0.1],
      model: CONFIG.expectedModel,
      modelRevision: CONFIG.expectedModelRevision,
      dimensions: 1,
      normalizedQueryText: "liquidity",
      latencyMs: 1,
      tokenCount: 1,
      provider: "test",
    });
    const caching = new CachingQueryEmbeddingProvider({ embedQuery }, queryEmbeddingCacheKeyPrefix(CONFIG));

    await caching.embedQuery("liquidity");
    await caching.embedQuery("liquidity");

    expect(embedQuery).toHaveBeenCalledTimes(1);
  });

  it("keys the cache by model/revision prefix so a different model never hits a stale entry", async () => {
    const first = vi.fn().mockResolvedValue({
      vector: [0.1],
      model: "model-a",
      modelRevision: "rev-a",
      dimensions: 1,
      normalizedQueryText: "liquidity",
      latencyMs: 1,
      tokenCount: 1,
      provider: "test",
    });
    const second = vi.fn().mockResolvedValue({
      vector: [0.2],
      model: "model-b",
      modelRevision: "rev-b",
      dimensions: 1,
      normalizedQueryText: "liquidity",
      latencyMs: 1,
      tokenCount: 1,
      provider: "test",
    });

    const providerA = new CachingQueryEmbeddingProvider({ embedQuery: first }, "model-a@rev-a");
    const providerB = new CachingQueryEmbeddingProvider({ embedQuery: second }, "model-b@rev-b");

    await providerA.embedQuery("liquidity");
    await providerB.embedQuery("liquidity");

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });
});
