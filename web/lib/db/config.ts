import "server-only";
import { DatabaseConfigError } from "./errors";

const ALLOWED_PROTOCOLS = new Set(["postgres:", "postgresql:"]);

export interface DatabaseConfig {
  connectionString: string;
  /** For display/logging only -- never the credential-bearing form. */
  redactedUrl: string;
  /** Raw `sslmode` query param, if any -- `pool.ts` decides the concrete
   * `ssl` option from this so SSL policy lives in exactly one place. */
  sslMode: string | null;
}

/**
 * Redacts a Postgres connection string down to `scheme://host:port/db` --
 * strips user, password, and query string entirely. Falls back to a fixed
 * placeholder if the value isn't parseable as a URL at all (e.g. someone
 * pasted a bare password), so a malformed value can never itself leak
 * through an error message.
 */
export function redactDatabaseUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    const port = url.port ? `:${url.port}` : "";
    return `${url.protocol}//${url.hostname}${port}${url.pathname}`;
  } catch {
    return "postgresql://<redacted>";
  }
}

/**
 * Reads and validates `APP_READONLY_DATABASE_URL` (or an explicit override,
 * used by tests to point at `TEST_APP_READONLY_DATABASE_URL` instead).
 * Throws `DatabaseConfigError` with a clear, redacted message when the
 * variable is absent or malformed -- this must fail loudly at startup/
 * first-use rather than silently falling back to any other credential
 * (research DB, publisher role, etc).
 */
export function loadDatabaseConfig(envValue: string | undefined = process.env.APP_READONLY_DATABASE_URL): DatabaseConfig {
  if (!envValue || envValue.trim().length === 0) {
    throw new DatabaseConfigError(
      "APP_READONLY_DATABASE_URL is not set. The application requires a read-only " +
        "connection string for the application (publication) database -- see docs/frontend.md.",
    );
  }

  let url: URL;
  try {
    url = new URL(envValue);
  } catch {
    throw new DatabaseConfigError(
      "APP_READONLY_DATABASE_URL is not a valid URL. Expected a postgresql:// connection string.",
    );
  }

  if (!ALLOWED_PROTOCOLS.has(url.protocol)) {
    throw new DatabaseConfigError(
      `APP_READONLY_DATABASE_URL has an unsupported scheme (${url.protocol}). Expected postgres:// or postgresql://.`,
    );
  }

  return {
    connectionString: envValue,
    redactedUrl: redactDatabaseUrl(envValue),
    sslMode: url.searchParams.get("sslmode"),
  };
}
