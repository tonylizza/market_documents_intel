import "server-only";
import { getPool } from "@/lib/db/pool";
import { toApplicationError } from "@/lib/db/errors";

const HNSW_EF_SEARCH = 40;

/**
 * Runs one parameterized vector query, optionally under HNSW search-mode
 * GUCs (`hnsw.iterative_scan`/`hnsw.ef_search`). `pool.query()` (the
 * ordinary helper in `lib/db/pool.ts`) can't be used for the HNSW case: a
 * plain (non-transaction-scoped) `SET` on a pooled connection would leak
 * into whatever unrelated query reuses that connection next. This checks
 * out one dedicated client, wraps the GUCs in an explicit transaction with
 * `SET LOCAL` (scoped to that transaction only), and always releases the
 * client back to the pool afterward.
 */
export async function queryVector<T>(
  sql: string,
  params: ReadonlyArray<unknown>,
  vectorSearchMode: "exact" | "hnsw",
): Promise<T[]> {
  const pool = getPool();
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
