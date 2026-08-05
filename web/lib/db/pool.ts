import "server-only";
import { Pool, type QueryResultRow } from "pg";
import "./type-parsers";
import { loadDatabaseConfig } from "./config";
import { toApplicationError } from "./errors";

/**
 * Single shared pool per server process -- never create a new `Pool` per
 * request (that would exhaust connections under load and defeats pooling
 * entirely). Cached on `globalThis` so Next.js dev-mode module reloading
 * (which re-executes this module on every edit) doesn't leak a fresh pool
 * on every hot reload.
 */
const POOL_MAX_CONNECTIONS = 5;
const STATEMENT_TIMEOUT_MS = 10_000;
const CONNECTION_TIMEOUT_MS = 5_000;

declare global {
  var __appReadonlyPool: Pool | undefined;
}

function createPool(): Pool {
  const config = loadDatabaseConfig();

  // Neon's serverless proxy routes a connection to the correct compute by
  // TLS SNI (see Neon's Node.js connection docs) -- `servername` is set
  // explicitly rather than left to Node's implicit derivation, which is
  // not guaranteed to match the connection-string host in every runtime
  // (observed live: identical connection string/role/grants succeeded via
  // psycopg but intermittently mis-resolved permissions via node-postgres
  // without an explicit `servername`, milestone 7B.3 Preview deployment).
  const host = new URL(config.connectionString).hostname;
  const ssl =
    config.sslMode === "require" || config.sslMode === "no-verify"
      ? { rejectUnauthorized: false, servername: host }
      : config.sslMode === "verify-full" || config.sslMode === "verify-ca"
        ? { rejectUnauthorized: true, servername: host }
        : undefined;

  return new Pool({
    connectionString: config.connectionString,
    max: POOL_MAX_CONNECTIONS,
    statement_timeout: STATEMENT_TIMEOUT_MS,
    connectionTimeoutMillis: CONNECTION_TIMEOUT_MS,
    ssl,
  });
}

export function getPool(): Pool {
  if (!globalThis.__appReadonlyPool) {
    globalThis.__appReadonlyPool = createPool();
  }
  return globalThis.__appReadonlyPool;
}

/**
 * Parameterized query helper -- the only way repositories should talk to
 * Postgres. Never accepts caller-built SQL fragments; `text` must be a
 * literal query string with `$1`/`$2`/... placeholders.
 */
export async function query<T extends QueryResultRow = QueryResultRow>(
  text: string,
  params: ReadonlyArray<unknown> = [],
): Promise<T[]> {
  const pool = getPool();
  try {
    const result = await pool.query<T>(text, params as unknown[]);
    return result.rows;
  } catch (error) {
    throw toApplicationError(error);
  }
}

/** Closes the pool cleanly -- used by test teardown, never in request handling. */
export async function closePool(): Promise<void> {
  if (globalThis.__appReadonlyPool) {
    await globalThis.__appReadonlyPool.end();
    globalThis.__appReadonlyPool = undefined;
  }
}
