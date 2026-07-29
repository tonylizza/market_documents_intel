/**
 * Frontend test database resolution -- mirrors the Python side's
 * `tests/conftest.py` convention exactly: an explicit env var always wins;
 * otherwise fall back to this repo's own local dev default (port 5434,
 * matching `docker-compose.yml`/`.env`). Never defaults to port 5433 (an
 * unrelated project's Postgres on this machine).
 */
const PORT = process.env.POSTGRES_PORT || "5434";

/** Read-only role connection string used by the app code under test. */
export const TEST_APP_READONLY_DATABASE_URL =
  process.env.TEST_APP_READONLY_DATABASE_URL ||
  `postgresql://app_readonly:test_readonly_pw_123@localhost:${PORT}/market_documents_app_test`;

/**
 * Elevated (publisher-equivalent) connection string used ONLY by the test
 * seed script to populate/reset fixture data -- never used by application
 * code, never used by `app_readonly`-scoped repository code under test.
 */
export const SEED_APP_DATABASE_URL =
  process.env.SEED_APP_DATABASE_URL ||
  `postgresql://market_documents:market_documents@localhost:${PORT}/market_documents_app_test`;
