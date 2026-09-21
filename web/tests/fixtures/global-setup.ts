import { spawnSync } from "node:child_process";
import path from "node:path";
import { SEED_APP_DATABASE_URL } from "./env";

/**
 * Track 7E.2b: runs once before the whole Vitest run (Vitest `globalSetup`,
 * not a per-file `beforeAll`) to re-apply `app_readonly`'s grants against
 * `market_documents_app_test` before any repository test connects.
 *
 * This exists because the grant set drifts out of sync with the schema on
 * a predictable cadence -- every migration that adds a new
 * `app.current_*` view (or another table `app_readonly` needs) requires a
 * grant re-run that nothing about `alembic upgrade head` performs
 * automatically. That drift previously required a human to notice
 * `DatabaseUnavailableError` in the repository suite and manually re-run
 * `market-documents publish app-init-roles` (docs/7d2c-healthcare
 * -services-review-production-promotion.md, docs/7e2-fresh-database
 * -release-rehearsal.md, both hit the identical gap independently). This
 * step makes that reproducible instead of tribal.
 *
 * Deliberately runs only `scripts/sql/app_grants.sql`, never the full
 * `app_roles.sql` -- the grants file creates or alters no role and touches
 * no password, so this can run unattended on every test invocation with no
 * risk to `app_readonly`/`app_publisher`'s cluster-wide password (shared
 * with `market_documents_app`, the real local dev database -- see
 * docs/frontend.md).
 */
export default async function globalSetup(): Promise<void> {
  const grantsScript = path.resolve(__dirname, "../../../scripts/sql/app_grants.sql");
  const result = spawnSync("psql", [SEED_APP_DATABASE_URL, "-v", "ON_ERROR_STOP=1", "-f", grantsScript], {
    encoding: "utf-8",
  });

  if (result.error) {
    throw new Error(
      `Could not run psql to refresh app_readonly grants on the frontend test database. ` +
        `Is psql installed and is the test database reachable at the SEED_APP_DATABASE_URL/POSTGRES_PORT ` +
        `this suite is configured with? (${result.error.message})`,
    );
  }
  if (result.status !== 0) {
    throw new Error(
      `Refreshing app_readonly grants on the frontend test database failed (scripts/sql/app_grants.sql, ` +
        `exit code ${result.status}):\n${result.stderr || result.stdout}`,
    );
  }
}
