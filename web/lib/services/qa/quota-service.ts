import "server-only";
import crypto from "node:crypto";
import { Pool } from "pg";

/**
 * Milestone 7B.3 abuse-control quota counters (brief: "approximately 10
 * generated answers per browser per day; approximately 100 generated
 * answers globally per day"). Talks to Neon exclusively through the
 * `qa_quota.increment_and_check` SECURITY DEFINER function via the
 * narrowly-scoped `app_quota_writer` role (see `scripts/sql/qa_quota.sql`)
 * -- this role has no table grants at all, so a compromised/buggy request
 * can never read or write anything beyond incrementing its own day's
 * counter. A completely separate connection pool from the main
 * `app_readonly` pool (`lib/db/pool.ts`); `app_readonly` itself is never
 * touched or widened by this feature.
 *
 * Failure behavior when the quota database itself is unavailable
 * (unconfigured/unreachable/timeout) is environment-sensitive, see
 * `loadQuotaFailureMode`: Production defaults to failing CLOSED (no Gemini
 * call, evidence/citations still returned) since an outage must never turn
 * into an unmetered answer-generation gate in the deployed app; Preview/dev
 * default to the original fail-OPEN behavior so a local/preview quota-db
 * hiccup never blocks testing the rest of the pipeline.
 */

const GLOBAL_KEY_HASH = "global";
const DEFAULT_PER_CLIENT_LIMIT = 10;
const DEFAULT_GLOBAL_LIMIT = 100;
const QUOTA_STATEMENT_TIMEOUT_MS = 3_000;
const QUOTA_CONNECTION_TIMEOUT_MS = 2_000;

declare global {
  var __qaQuotaPool: Pool | undefined;
}

function getPool(): Pool | null {
  const connectionString = process.env.QA_QUOTA_DATABASE_URL;
  if (!connectionString) return null;
  if (!globalThis.__qaQuotaPool) {
    globalThis.__qaQuotaPool = new Pool({
      connectionString,
      max: 3,
      statement_timeout: QUOTA_STATEMENT_TIMEOUT_MS,
      connectionTimeoutMillis: QUOTA_CONNECTION_TIMEOUT_MS,
      ssl: { rejectUnauthorized: false },
    });
  }
  return globalThis.__qaQuotaPool;
}

/** Never derived from IP -- hashes the opaque, random first-party cookie
 * value assigned by `middleware.ts`. Privacy-conscious per the brief
 * ("hashed identifiers rather than storing raw IP addresses"): even the
 * cookie value itself never reaches the database, only its digest. */
export function hashClientId(rawClientId: string): string {
  return crypto.createHash("sha256").update(rawClientId).digest("hex");
}

export interface QuotaCheckResult {
  allowed: boolean;
  reason: "within_limit" | "per_client_limit" | "global_limit" | "quota_service_unavailable";
}

export type QuotaFailureMode = "open" | "closed";

const QUOTA_FAILURE_MODES: readonly QuotaFailureMode[] = ["open", "closed"];

function isProductionEnvironment(): boolean {
  // `VERCEL_ENV`, not `NODE_ENV` -- a Next.js production build always sets
  // `NODE_ENV=production` for Preview deployments too, so only `VERCEL_ENV`
  // actually distinguishes the deployed Production environment from
  // Preview/local. Unset (local dev, `next test`) is never treated as
  // Production.
  return process.env.VERCEL_ENV === "production";
}

/**
 * Validates `QA_QUOTA_FAILURE_MODE`. Unset or unrecognized values default
 * safely per environment: "closed" in Production (fail closed -- an
 * unavailable quota database must never silently become an unmetered
 * Gemini gate), "open" everywhere else (preserves the original fail-open
 * behavior for Preview/dev). Never throws -- an invalid value is logged and
 * degrades to the safe per-environment default rather than crashing `/ask`.
 */
export function loadQuotaFailureMode(): QuotaFailureMode {
  const raw = process.env.QA_QUOTA_FAILURE_MODE?.trim().toLowerCase();
  if (raw === undefined || raw === "") {
    return isProductionEnvironment() ? "closed" : "open";
  }
  if ((QUOTA_FAILURE_MODES as string[]).includes(raw)) {
    return raw as QuotaFailureMode;
  }
  const fallback = isProductionEnvironment() ? "closed" : "open";
  console.error(`qa_quota: invalid QA_QUOTA_FAILURE_MODE "${raw}", defaulting to "${fallback}"`);
  return fallback;
}

function unavailableResult(): QuotaCheckResult {
  return { allowed: loadQuotaFailureMode() === "open", reason: "quota_service_unavailable" };
}

/**
 * Checks and atomically increments both the per-client and global daily
 * counters. On any connectivity/timeout/config problem, degrades according
 * to `loadQuotaFailureMode()` -- see module docstring. This remains a
 * defense-in-depth abuse control, not the primary access gate (there is
 * none, per the brief: "do not add authentication or user accounts"); it
 * gates only whether Gemini is called, never retrieval/evidence.
 */
export async function checkAndIncrementQuota(
  clientIdHash: string,
  perClientLimit = DEFAULT_PER_CLIENT_LIMIT,
  globalLimit = DEFAULT_GLOBAL_LIMIT,
): Promise<QuotaCheckResult> {
  const pool = getPool();
  if (!pool) {
    return unavailableResult();
  }

  try {
    const clientResult = await pool.query<{ allowed: boolean; current_count: number }>(
      "SELECT allowed, current_count FROM qa_quota.increment_and_check($1, $2, $3)",
      ["client", clientIdHash, perClientLimit],
    );
    if (!clientResult.rows[0]?.allowed) {
      return { allowed: false, reason: "per_client_limit" };
    }

    const globalResult = await pool.query<{ allowed: boolean; current_count: number }>(
      "SELECT allowed, current_count FROM qa_quota.increment_and_check($1, $2, $3)",
      ["global", GLOBAL_KEY_HASH, globalLimit],
    );
    if (!globalResult.rows[0]?.allowed) {
      return { allowed: false, reason: "global_limit" };
    }

    return { allowed: true, reason: "within_limit" };
  } catch (error) {
    // Never logs query contents (there are none here beyond the hash/
    // limits) -- just the failure itself, for operational visibility. The
    // raw error (which can include connection strings/hostnames) never
    // reaches the browser -- only this redacted message hits server logs,
    // and callers only ever see the `quota_service_unavailable` reason.
    console.error("qa_quota check failed:", (error as Error).message);
    return unavailableResult();
  }
}

export function loadQuotaLimits(): { perClientLimit: number; globalLimit: number } {
  const perClientLimit = Number.parseInt(process.env.QA_QUOTA_PER_CLIENT_DAILY ?? "", 10);
  const globalLimit = Number.parseInt(process.env.QA_QUOTA_GLOBAL_DAILY ?? "", 10);
  return {
    perClientLimit: Number.isFinite(perClientLimit) && perClientLimit > 0 ? perClientLimit : DEFAULT_PER_CLIENT_LIMIT,
    globalLimit: Number.isFinite(globalLimit) && globalLimit > 0 ? globalLimit : DEFAULT_GLOBAL_LIMIT,
  };
}
