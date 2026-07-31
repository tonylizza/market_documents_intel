import "server-only";

/**
 * Milestone 7B.2 grounded-generation provider configuration. Server-only,
 * environment-based secrets (brief: "environment-based secrets") -- the API
 * key is never read anywhere client-side and never appears in a response.
 */

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export interface GenerationConfig {
  apiKey: string | null;
  model: string;
  timeoutMs: number;
  /** Number of retries AFTER the first attempt -- bounded, never unbounded
   * (brief: "bounded retries"). */
  maxRetries: number;
  retryBackoffMs: number;
}

export function getGenerationConfig(): GenerationConfig {
  return {
    apiKey: process.env.GEMINI_API_KEY ?? null,
    // "gemini-2.5-flash-lite" (the originally chosen pinned version) was
    // confirmed live to 404 as "no longer available to new users" despite
    // still being listed by the models endpoint -- the "-latest" alias
    // tracks whatever lite model Google currently serves for this API
    // version, avoiding the same class of silent deprecation breakage.
    model: process.env.GEMINI_MODEL ?? "gemini-flash-lite-latest",
    timeoutMs: envInt("GEMINI_TIMEOUT_MS", 15_000),
    maxRetries: envInt("GEMINI_MAX_RETRIES", 1),
    retryBackoffMs: envInt("GEMINI_RETRY_BACKOFF_MS", 500),
  };
}
