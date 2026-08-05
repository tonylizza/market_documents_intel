import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CachingQueryEmbeddingProvider,
  CloudflareQueryEmbeddingProvider,
  HttpQueryEmbeddingProvider,
  QueryEmbeddingModelMismatchError,
  QueryEmbeddingProviderError,
  createQueryEmbeddingProvider,
  queryEmbeddingCacheKeyPrefix,
  resolveQueryEmbeddingProviderSelector,
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

const CF_CONFIG = {
  accountId: "test-account",
  apiToken: "test-token",
  model: "@cf/baai/bge-small-en-v1.5",
  timeoutMs: 5000,
  expectedDimensions: 384,
  maxQueryChars: 2000,
  debugLogQueries: false,
};

function mockCfFetch(response: unknown, ok = true, status = 200) {
  const fn = vi.fn().mockResolvedValue({ ok, status, json: async () => response });
  global.fetch = fn as unknown as typeof fetch;
  return fn;
}

function cfBody(overrides: Partial<{ success: boolean; data: number[][] }> = {}) {
  return {
    success: true,
    result: { data: overrides.data ?? [new Array(384).fill(0.05)], shape: [1, 384], pooling: "mean" },
    errors: [],
    messages: [],
  };
}

describe("CloudflareQueryEmbeddingProvider", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns a validated, L2-normalized QueryEmbedding on success", async () => {
    mockCfFetch(cfBody());
    const provider = new CloudflareQueryEmbeddingProvider(CF_CONFIG);
    const result = await provider.embedQuery("liquidity risk");
    expect(result.vector).toHaveLength(384);
    expect(result.provider).toBe("cloudflare-workers-ai");
    expect(result.model).toBe(CF_CONFIG.model);
    const norm = Math.sqrt(result.vector.reduce((s, x) => s + x * x, 0));
    expect(norm).toBeCloseTo(1, 5);
  });

  it("throws QueryEmbeddingModelMismatchError on dimension mismatch", async () => {
    mockCfFetch(cfBody({ data: [new Array(128).fill(0.1)] }));
    const provider = new CloudflareQueryEmbeddingProvider(CF_CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingModelMismatchError);
  });

  it("rejects an oversized query without calling the network", async () => {
    const fetchMock = mockCfFetch(cfBody());
    const provider = new CloudflareQueryEmbeddingProvider({ ...CF_CONFIG, maxQueryChars: 5 });
    await expect(provider.embedQuery("this is way too long")).rejects.toBeInstanceOf(QueryEmbeddingProviderError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not retry on 401/403", async () => {
    const fetchMock = mockCfFetch({}, false, 401);
    const provider = new CloudflareQueryEmbeddingProvider(CF_CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingProviderError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not retry on 429", async () => {
    const fetchMock = mockCfFetch({}, false, 429);
    const provider = new CloudflareQueryEmbeddingProvider(CF_CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingProviderError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retries exactly once on a transient 500, then succeeds", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) })
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => cfBody() });
    global.fetch = fetchMock as unknown as typeof fetch;
    const provider = new CloudflareQueryEmbeddingProvider(CF_CONFIG);
    const result = await provider.embedQuery("liquidity");
    expect(result.vector).toHaveLength(384);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("gives up after one retry on a persistent transient failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) });
    global.fetch = fetchMock as unknown as typeof fetch;
    const provider = new CloudflareQueryEmbeddingProvider(CF_CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingProviderError);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("throws QueryEmbeddingProviderError on a malformed response", async () => {
    mockCfFetch({ success: false, errors: ["boom"] });
    const provider = new CloudflareQueryEmbeddingProvider(CF_CONFIG);
    await expect(provider.embedQuery("x")).rejects.toBeInstanceOf(QueryEmbeddingProviderError);
  });
});

describe("createQueryEmbeddingProvider / resolveQueryEmbeddingProviderSelector", () => {
  const originalEnv = { ...process.env };

  afterEach(() => {
    process.env = { ...originalEnv };
  });

  it("defaults to the local provider when QUERY_EMBEDDING_PROVIDER is unset", () => {
    delete process.env.QUERY_EMBEDDING_PROVIDER;
    expect(resolveQueryEmbeddingProviderSelector()).toBe("local");
  });

  it("selects cloudflare when QUERY_EMBEDDING_PROVIDER=cloudflare", () => {
    process.env.QUERY_EMBEDDING_PROVIDER = "cloudflare";
    expect(resolveQueryEmbeddingProviderSelector()).toBe("cloudflare");
  });

  it("rejects an unknown provider selector", () => {
    process.env.QUERY_EMBEDDING_PROVIDER = "openai";
    expect(() => resolveQueryEmbeddingProviderSelector()).toThrow(QueryEmbeddingProviderError);
  });

  it("createQueryEmbeddingProvider throws clearly when cloudflare is selected but unconfigured", () => {
    process.env.QUERY_EMBEDDING_PROVIDER = "cloudflare";
    delete process.env.CLOUDFLARE_ACCOUNT_ID;
    delete process.env.CLOUDFLARE_API_TOKEN;
    expect(() => createQueryEmbeddingProvider()).toThrow(QueryEmbeddingProviderError);
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
