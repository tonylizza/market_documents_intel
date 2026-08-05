import "server-only";
import type { QueryEmbedding } from "@/lib/domain/retrieval";

/**
 * Server-side-only boundary for turning free-text search input into a
 * vector. The browser never calls this directly -- see `docs/frontend.md`'s
 * "Database-access architecture" note and this module's `server-only`
 * import guard (enforced by the same static-scan test pattern as
 * `lib/db/pool.ts`, see `tests/unit/no-client-db-imports.test.ts`).
 */
export interface QueryEmbeddingProvider {
  embedQuery(text: string): Promise<QueryEmbedding>;
}

export class QueryEmbeddingProviderError extends Error {
  constructor(
    message: string,
    readonly cause_?: unknown,
  ) {
    super(message);
    this.name = "QueryEmbeddingProviderError";
  }
}

export class QueryEmbeddingModelMismatchError extends QueryEmbeddingProviderError {
  constructor(message: string) {
    super(message);
    this.name = "QueryEmbeddingModelMismatchError";
  }
}

export interface HttpQueryEmbeddingProviderConfig {
  serviceUrl: string;
  timeoutMs: number;
  expectedModel: string;
  expectedModelRevision: string;
  expectedDimensions: number;
}

export function loadHttpQueryEmbeddingProviderConfig(): HttpQueryEmbeddingProviderConfig {
  const serviceUrl = process.env.QUERY_EMBEDDING_SERVICE_URL;
  if (!serviceUrl) {
    throw new QueryEmbeddingProviderError(
      "QUERY_EMBEDDING_SERVICE_URL is not set. Semantic/hybrid search requires the query-embedding service.",
    );
  }
  return {
    serviceUrl,
    timeoutMs: Number.parseInt(process.env.QUERY_EMBEDDING_TIMEOUT_MS ?? "8000", 10),
    // Must match the corpus's stored embedding model/revision/dimension
    // exactly (see `services/embedding_config.py`) -- a mismatch here means
    // query vectors would not be comparable to the stored corpus vectors.
    expectedModel: process.env.QUERY_EMBEDDING_MODEL ?? "BAAI/bge-small-en-v1.5",
    expectedModelRevision: process.env.QUERY_EMBEDDING_MODEL_REVISION ?? "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
    expectedDimensions: Number.parseInt(process.env.QUERY_EMBEDDING_DIMENSIONS ?? "384", 10),
  };
}

interface EmbedQueryHttpResponse {
  vector: number[];
  model: string;
  model_revision: string;
  dimensions: number;
  normalized_text: string;
  token_count: number;
  latency_ms: number;
  provider: string;
}

/**
 * Calls the standalone Python embedding service's `POST /embed-query`
 * (see `market_documents.embedding_service.app`). No query text is ever
 * sent anywhere other than this configured, first-party, local/self-hosted
 * service -- there is no external/hosted-provider code path in this
 * milestone (see the "External-provider privacy" section of the
 * milestone brief).
 */
export class HttpQueryEmbeddingProvider implements QueryEmbeddingProvider {
  constructor(private readonly config: HttpQueryEmbeddingProviderConfig = loadHttpQueryEmbeddingProviderConfig()) {}

  async embedQuery(text: string): Promise<QueryEmbedding> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.config.timeoutMs);

    let response: Response;
    try {
      response = await fetch(`${this.config.serviceUrl}/embed-query`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
        signal: controller.signal,
      });
    } catch (error) {
      throw new QueryEmbeddingProviderError("Query-embedding service is unavailable.", error);
    } finally {
      clearTimeout(timeout);
    }

    if (!response.ok) {
      let detail = "";
      try {
        const body = (await response.json()) as { detail?: string };
        detail = body.detail ?? "";
      } catch {
        // Response body wasn't JSON -- fall through with an empty detail
        // rather than letting a raw parse error surface.
      }
      throw new QueryEmbeddingProviderError(
        `Query-embedding service returned ${response.status}${detail ? `: ${detail}` : ""}`,
      );
    }

    const body = (await response.json()) as EmbedQueryHttpResponse;

    if (body.model !== this.config.expectedModel || body.model_revision !== this.config.expectedModelRevision) {
      throw new QueryEmbeddingModelMismatchError(
        `Query-embedding model mismatch: service returned ${body.model}@${body.model_revision}, ` +
          `expected ${this.config.expectedModel}@${this.config.expectedModelRevision}.`,
      );
    }
    if (body.dimensions !== this.config.expectedDimensions || body.vector.length !== this.config.expectedDimensions) {
      throw new QueryEmbeddingModelMismatchError(
        `Query-embedding dimension mismatch: service returned ${body.dimensions}, expected ${this.config.expectedDimensions}.`,
      );
    }

    return {
      vector: body.vector,
      model: body.model,
      modelRevision: body.model_revision,
      dimensions: body.dimensions,
      normalizedQueryText: body.normalized_text,
      latencyMs: body.latency_ms,
      tokenCount: body.token_count,
      provider: body.provider,
    } satisfies QueryEmbedding;
  }
}

export interface CloudflareQueryEmbeddingProviderConfig {
  accountId: string;
  apiToken: string;
  model: string;
  timeoutMs: number;
  expectedDimensions: number;
  maxQueryChars: number;
  debugLogQueries: boolean;
}

export function loadCloudflareQueryEmbeddingProviderConfig(): CloudflareQueryEmbeddingProviderConfig {
  const accountId = process.env.CLOUDFLARE_ACCOUNT_ID;
  const apiToken = process.env.CLOUDFLARE_API_TOKEN;
  if (!accountId || !apiToken) {
    throw new QueryEmbeddingProviderError(
      "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN must both be set for the Cloudflare query-embedding provider.",
    );
  }
  return {
    accountId,
    apiToken,
    // Exact production model identifier -- never client-selectable (see
    // Phase 4/5 compatibility experiment: mean-pooling vs. the corpus's
    // canonical CLS-pooling local model, accepted on measured retrieval
    // quality, not byte-identical output).
    model: process.env.CLOUDFLARE_EMBEDDING_MODEL ?? "@cf/baai/bge-small-en-v1.5",
    timeoutMs: Number.parseInt(process.env.QUERY_EMBEDDING_TIMEOUT_MS ?? "8000", 10),
    expectedDimensions: Number.parseInt(process.env.QUERY_EMBEDDING_DIMENSIONS ?? "384", 10),
    maxQueryChars: Number.parseInt(process.env.QUERY_EMBEDDING_MAX_QUERY_CHARS ?? "2000", 10),
    // Off by default -- query text must never enter production logs unless
    // explicitly opted into for debugging (milestone constraint).
    debugLogQueries: process.env.QUERY_EMBEDDING_DEBUG_LOG === "true",
  };
}

/** Retryable (network/timeout/5xx) failure -- distinguished from auth/quota/
 * malformed-output failures below, which must never be retried. Still a
 * `QueryEmbeddingProviderError` so existing `instanceof` call sites keep
 * working unchanged after the bounded retry is exhausted. */
class CloudflareTransientError extends QueryEmbeddingProviderError {
  constructor(message: string) {
    super(message);
    this.name = "CloudflareTransientError";
  }
}

/**
 * Server-side Cloudflare Workers AI implementation of `QueryEmbeddingProvider`
 * (Milestone 7B.3). Calls the REST `ai/run` endpoint directly from the
 * Next.js server -- no separate Cloudflare Worker, no client-selectable
 * model, no raw vector ever returned to the browser (this class is only
 * ever invoked from other server-only modules). At most one bounded retry
 * on a transient failure; 401/403/429 and malformed/invalid-dimension
 * output fail immediately, never retried.
 */
export class CloudflareQueryEmbeddingProvider implements QueryEmbeddingProvider {
  constructor(private readonly config: CloudflareQueryEmbeddingProviderConfig = loadCloudflareQueryEmbeddingProviderConfig()) {}

  async embedQuery(text: string): Promise<QueryEmbedding> {
    const normalized = text.replace(/\s+/g, " ").trim();
    if (!normalized) {
      throw new QueryEmbeddingProviderError("query text is empty after normalization");
    }
    if (normalized.length > this.config.maxQueryChars) {
      throw new QueryEmbeddingProviderError(
        `query text exceeds maximum length of ${this.config.maxQueryChars} characters`,
      );
    }

    try {
      return await this.callOnce(normalized);
    } catch (error) {
      if (error instanceof CloudflareTransientError) {
        // One bounded retry, transient failures only.
        return await this.callOnce(normalized);
      }
      throw error;
    }
  }

  private async callOnce(normalized: string): Promise<QueryEmbedding> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.config.timeoutMs);
    const start = Date.now();

    let response: Response;
    try {
      response = await fetch(
        `https://api.cloudflare.com/client/v4/accounts/${this.config.accountId}/ai/run/${this.config.model}`,
        {
          method: "POST",
          headers: {
            authorization: `Bearer ${this.config.apiToken}`,
            "content-type": "application/json",
          },
          body: JSON.stringify({ text: [normalized] }),
          signal: controller.signal,
          // Never cached -- a live query embedding must always be a fresh call.
          cache: "no-store",
        },
      );
    } catch (error) {
      clearTimeout(timeout);
      if ((error as { name?: string })?.name === "AbortError") {
        throw new CloudflareTransientError("Cloudflare embedding request timed out.");
      }
      throw new CloudflareTransientError("Cloudflare embedding service is unavailable.");
    }
    clearTimeout(timeout);

    if (response.status === 401 || response.status === 403) {
      // Never retried -- a bad/expired token won't fix itself on retry.
      throw new QueryEmbeddingProviderError(`Cloudflare embedding request rejected (HTTP ${response.status}).`);
    }
    if (response.status === 429) {
      // Never retried -- retrying a quota error only makes it worse.
      throw new QueryEmbeddingProviderError("Cloudflare embedding quota exceeded.");
    }
    if (!response.ok) {
      throw new CloudflareTransientError(`Cloudflare embedding service returned HTTP ${response.status}.`);
    }

    let body: { success?: boolean; result?: { data?: unknown[] } };
    try {
      body = await response.json();
    } catch {
      throw new QueryEmbeddingProviderError("Cloudflare embedding response was not valid JSON.");
    }

    const vectorRaw = body?.result?.data?.[0];
    if (!body?.success || !Array.isArray(vectorRaw) || vectorRaw.length === 0) {
      throw new QueryEmbeddingProviderError("Cloudflare embedding response was malformed.");
    }
    if (vectorRaw.length !== this.config.expectedDimensions || !vectorRaw.every((x) => typeof x === "number" && Number.isFinite(x))) {
      throw new QueryEmbeddingModelMismatchError(
        `Cloudflare embedding dimension/validity mismatch: got ${vectorRaw.length} values, expected ${this.config.expectedDimensions} finite numbers.`,
      );
    }
    const numericVector = vectorRaw as number[];

    // Deterministic normalization -- Cloudflare's output is already
    // near-unit-norm (measured 1.0 +/- ~0.0002 in the Phase 4 compatibility
    // experiment) but is not guaranteed exactly 1.0, and the stored corpus
    // vectors are always exactly L2-normalized (see `embedding_config.py`).
    const norm = Math.sqrt(numericVector.reduce((sum, x) => sum + x * x, 0));
    if (!(norm > 0)) {
      throw new QueryEmbeddingProviderError("Cloudflare embedding vector had zero norm.");
    }
    const vector = numericVector.map((x) => x / norm);

    if (this.config.debugLogQueries) {
      console.debug("[cloudflare-query-embedding]", { latencyMs: Date.now() - start, normalizedTextLength: normalized.length });
    }

    return {
      vector,
      model: this.config.model,
      // Cloudflare's response carries no revision/version identifier for
      // the underlying weights (unlike the local FastAPI service's
      // `model_revision`) -- "workers-ai" documents the provider surface
      // itself rather than asserting a specific pinned revision.
      modelRevision: "workers-ai",
      dimensions: vector.length,
      normalizedQueryText: normalized,
      latencyMs: Date.now() - start,
      tokenCount: null,
      provider: "cloudflare-workers-ai",
    } satisfies QueryEmbedding;
  }
}

export type QueryEmbeddingProviderSelector = "local" | "cloudflare";

export function resolveQueryEmbeddingProviderSelector(): QueryEmbeddingProviderSelector {
  const raw = (process.env.QUERY_EMBEDDING_PROVIDER ?? "local").trim().toLowerCase();
  if (raw === "cloudflare") return "cloudflare";
  if (raw === "local") return "local";
  throw new QueryEmbeddingProviderError(`Unknown QUERY_EMBEDDING_PROVIDER "${raw}"; expected "local" or "cloudflare".`);
}

/** Single construction point for every `/ask` and `/evidence-review`
 * caller -- deployment-level `QUERY_EMBEDDING_PROVIDER` selects local vs.
 * Cloudflare; never a per-request/client-selectable choice. Always wraps
 * the inner provider in the existing in-process LRU cache. */
export function createQueryEmbeddingProvider(): QueryEmbeddingProvider {
  if (resolveQueryEmbeddingProviderSelector() === "cloudflare") {
    const config = loadCloudflareQueryEmbeddingProviderConfig();
    return new CachingQueryEmbeddingProvider(new CloudflareQueryEmbeddingProvider(config), `cloudflare:${config.model}`);
  }
  const config = loadHttpQueryEmbeddingProviderConfig();
  return new CachingQueryEmbeddingProvider(new HttpQueryEmbeddingProvider(config), queryEmbeddingCacheKeyPrefix(config));
}

const QUERY_EMBEDDING_CACHE_MAX_ENTRIES = 200;

declare global {
  var __queryEmbeddingCache: Map<string, QueryEmbedding> | undefined;
}

function getCache(): Map<string, QueryEmbedding> {
  globalThis.__queryEmbeddingCache ??= new Map();
  return globalThis.__queryEmbeddingCache;
}

/** Small in-process LRU for query embeddings, keyed by the *raw* input text
 * (not the service-normalized text, which is only known after a call) plus
 * `expectedModel`/`expectedModelRevision` so a model/revision change can
 * never serve a stale vector under a cache hit (see milestone: "never cache
 * across model-version mismatch"). A cache hit skips the HTTP call
 * entirely; a miss falls through to the inner provider and is then cached.
 * Acceptable for conventional Node deployment; not depended on for
 * correctness (a cold cache/serverless restart just means a cache miss,
 * not an error). */
export class CachingQueryEmbeddingProvider implements QueryEmbeddingProvider {
  constructor(
    private readonly inner: QueryEmbeddingProvider,
    private readonly cacheKeyPrefix: string = "default",
  ) {}

  async embedQuery(text: string): Promise<QueryEmbedding> {
    const cache = getCache();
    const cacheKey = `${this.cacheKeyPrefix}:${text}`;

    const cached = cache.get(cacheKey);
    if (cached) {
      cache.delete(cacheKey);
      cache.set(cacheKey, cached);
      return cached;
    }

    const embedding = await this.inner.embedQuery(text);
    if (cache.size >= QUERY_EMBEDDING_CACHE_MAX_ENTRIES) {
      const oldestKey = cache.keys().next().value;
      if (oldestKey !== undefined) cache.delete(oldestKey);
    }
    cache.set(cacheKey, embedding);
    return embedding;
  }
}

/** Builds the cache-key prefix from the configured model/revision so a
 * deployment change is reflected automatically -- callers should construct
 * `CachingQueryEmbeddingProvider` with this rather than a literal string. */
export function queryEmbeddingCacheKeyPrefix(config: HttpQueryEmbeddingProviderConfig): string {
  return `${config.expectedModel}@${config.expectedModelRevision}`;
}
