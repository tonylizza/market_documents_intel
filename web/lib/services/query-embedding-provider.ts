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
