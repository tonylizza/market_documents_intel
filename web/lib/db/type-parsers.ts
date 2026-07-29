import "server-only";
import { types } from "pg";

/**
 * `pg` parses Postgres `date` columns (OID 1082) into JS `Date` objects by
 * default, which silently shifts by the server's local timezone on
 * `.toISOString()` -- a pure calendar date (period_end, with no time
 * component) must round-trip as the exact string Postgres sent, never
 * reinterpreted through a timezone. Applied once at module load, before
 * any query runs (imported for its side effect by `pool.ts`).
 */
const DATE_OID = 1082;
types.setTypeParser(DATE_OID, (value: string) => value);
