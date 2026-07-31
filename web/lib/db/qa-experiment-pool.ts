import "server-only";
import { Pool, type QueryResultRow } from "pg";
import "./type-parsers";
import { loadDatabaseConfig } from "./config";
import { toApplicationError } from "./errors";

/**
 * Milestone 7B.1d (experimental): a dedicated pool for the disposable
 * `qa_experiment.*` schema, deliberately separate from `lib/db/pool.ts`'s
 * shared `app_readonly`-bound pool.
 *
 * `app_readonly` is never granted access to `qa_experiment.*` (see
 * `scripts/sql/qa_experiment_schema.sql`'s header comment and the milestone
 * brief: "app_readonly may read approved current views only, not raw chunk
 * tables") -- that role is also what production `/evidence-review` and
 * every public route runs as, so granting it broader access here would
 * silently widen what a compromised or buggy production request could
 * reach. Only evaluation scripts (never imported by any `app/` route) use
 * this module, pointed at a distinct, higher-privilege connection string
 * via `QA_EXPERIMENT_DATABASE_URL` (in practice the same `app_publisher`-
 * equivalent credential the Python build script uses).
 */

const POOL_MAX_CONNECTIONS = 5;
const STATEMENT_TIMEOUT_MS = 30_000;
const CONNECTION_TIMEOUT_MS = 5_000;
const HNSW_EF_SEARCH = 40;

declare global {
  var __qaExperimentPool: Pool | undefined;
}

function createPool(): Pool {
  const config = loadDatabaseConfig(process.env.QA_EXPERIMENT_DATABASE_URL);

  const ssl =
    config.sslMode === "require" || config.sslMode === "no-verify"
      ? { rejectUnauthorized: false }
      : config.sslMode === "verify-full" || config.sslMode === "verify-ca"
        ? { rejectUnauthorized: true }
        : undefined;

  return new Pool({
    connectionString: config.connectionString,
    max: POOL_MAX_CONNECTIONS,
    statement_timeout: STATEMENT_TIMEOUT_MS,
    connectionTimeoutMillis: CONNECTION_TIMEOUT_MS,
    ssl,
  });
}

export function getQaExperimentPool(): Pool {
  if (!globalThis.__qaExperimentPool) {
    globalThis.__qaExperimentPool = createPool();
  }
  return globalThis.__qaExperimentPool;
}

export async function qaExperimentQuery<T extends QueryResultRow = QueryResultRow>(
  text: string,
  params: ReadonlyArray<unknown> = [],
): Promise<T[]> {
  const pool = getQaExperimentPool();
  try {
    const result = await pool.query<T>(text, params as unknown[]);
    return result.rows;
  } catch (error) {
    throw toApplicationError(error);
  }
}

/** Same HNSW-scoping pattern as `lib/db/vector-query.ts::queryVector`, on
 * the dedicated pool. */
export async function qaExperimentQueryVector<T>(
  sql: string,
  params: ReadonlyArray<unknown>,
  vectorSearchMode: "exact" | "hnsw",
): Promise<T[]> {
  const pool = getQaExperimentPool();
  const client = await pool.connect();
  try {
    if (vectorSearchMode === "hnsw") {
      await client.query("BEGIN");
      try {
        await client.query("SET LOCAL hnsw.iterative_scan = relaxed_order");
        await client.query(`SET LOCAL hnsw.ef_search = ${HNSW_EF_SEARCH}`);
        const result = await client.query(sql, params as unknown[]);
        await client.query("COMMIT");
        return result.rows as T[];
      } catch (error) {
        await client.query("ROLLBACK");
        throw error;
      }
    }
    const result = await client.query(sql, params as unknown[]);
    return result.rows as T[];
  } catch (error) {
    throw toApplicationError(error);
  } finally {
    client.release();
  }
}

export async function closeQaExperimentPool(): Promise<void> {
  if (globalThis.__qaExperimentPool) {
    await globalThis.__qaExperimentPool.end();
    globalThis.__qaExperimentPool = undefined;
  }
}
