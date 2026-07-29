import { type ChildProcess, spawn, spawnSync } from "node:child_process";
import path from "node:path";
import { Client } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { seedAppDatabase } from "../fixtures/seed-app-database";
import { TEST_APP_READONLY_DATABASE_URL, SEED_APP_DATABASE_URL } from "../fixtures/env";

/**
 * Verifies the actual raw HTTP status code returned by a real `next
 * build`/`next start` production server -- not just the not-found UI's
 * presence in a 200 response. This is the milestone's core regression test
 * for the pre-existing bug: a blanket root `app/loading.tsx` Suspense
 * boundary forced every route (including ones that call `notFound()`) to
 * flush an initial 200 response before the page's own async work resolved.
 * The fix (see `app/(home)/loading.tsx`, `app/discover/loading.tsx`,
 * `app/methodology/loading.tsx`, `app/passages/loading.tsx`, and the
 * removal of the old blanket `app/loading.tsx`) means the four dynamic
 * routes under test here now have *no* loading boundary in their ancestor
 * chain, so `next start` can send a real 404 status.
 *
 * Runs against the dedicated frontend test database/fixture (never the
 * real local `market_documents_app`), so this test is fully self-contained
 * and deterministic.
 */
const WEB_ROOT = path.resolve(__dirname, "../..");
const PORT = 3417;
const BASE_URL = `http://127.0.0.1:${PORT}`;
const BUILD_TIMEOUT_MS = 240_000;
const SERVER_READY_TIMEOUT_MS = 60_000;

let serverProcess: ChildProcess | null = null;
let validTicker: string;
let validComparisonId: string;
let validPassageComparisonId: string;
const invalidUuid = "00000000-0000-0000-0000-000000000000";

async function waitForServerReady(): Promise<void> {
  const deadline = Date.now() + SERVER_READY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE_URL}/`);
      if (response.status > 0) return;
    } catch {
      // Server not accepting connections yet -- keep polling.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("Production server did not become ready in time");
}

beforeAll(async () => {
  await seedAppDatabase();

  const client = new Client({ connectionString: SEED_APP_DATABASE_URL });
  await client.connect();
  try {
    const companyRow = await client.query<{ ticker: string }>(
      `SELECT ticker FROM app.current_companies WHERE ticker = 'ACT' LIMIT 1`,
    );
    validTicker = companyRow.rows[0].ticker;

    const comparisonRow = await client.query<{ id: string }>(
      `SELECT rc.id FROM app.current_report_comparisons rc
       JOIN app.current_companies c ON c.id = rc.company_id
       WHERE c.ticker = 'ACT' AND rc.is_latest_for_company = true LIMIT 1`,
    );
    validComparisonId = comparisonRow.rows[0].id;

    const passageComparisonRow = await client.query<{ id: string }>(
      `SELECT id FROM app.current_passage_comparisons WHERE report_comparison_id = $1 LIMIT 1`,
      [validComparisonId],
    );
    validPassageComparisonId = passageComparisonRow.rows[0].id;
  } finally {
    await client.end();
  }

  const buildEnv = { ...process.env, APP_READONLY_DATABASE_URL: TEST_APP_READONLY_DATABASE_URL };

  const build = spawnSync("pnpm", ["exec", "next", "build"], {
    cwd: WEB_ROOT,
    env: buildEnv,
    stdio: "pipe",
    timeout: BUILD_TIMEOUT_MS,
  });
  if (build.status !== 0) {
    throw new Error(`next build failed:\n${build.stdout?.toString()}\n${build.stderr?.toString()}`);
  }

  serverProcess = spawn("pnpm", ["exec", "next", "start", "-p", String(PORT)], {
    cwd: WEB_ROOT,
    env: buildEnv,
    stdio: "pipe",
  });
  await waitForServerReady();
}, BUILD_TIMEOUT_MS + SERVER_READY_TIMEOUT_MS);

afterAll(async () => {
  if (serverProcess) {
    serverProcess.kill();
  }
});

describe("production HTTP status codes (real next build + next start)", () => {
  it("GET / returns 200", async () => {
    const response = await fetch(`${BASE_URL}/`);
    expect(response.status).toBe(200);
  });

  it("GET /discover returns 200", async () => {
    const response = await fetch(`${BASE_URL}/discover`);
    expect(response.status).toBe(200);
  });

  it("GET /methodology returns 200", async () => {
    const response = await fetch(`${BASE_URL}/methodology`);
    expect(response.status).toBe(200);
  });

  it("GET /passages returns 200 (orientation state, no query)", async () => {
    const response = await fetch(`${BASE_URL}/passages`);
    expect(response.status).toBe(200);
  });

  it("GET /passages?q=liquidity returns 200", async () => {
    const response = await fetch(`${BASE_URL}/passages?q=liquidity`);
    expect(response.status).toBe(200);
  });

  it("GET /companies/[validTicker] returns 200", async () => {
    const response = await fetch(`${BASE_URL}/companies/${validTicker}`);
    expect(response.status).toBe(200);
  });

  it("GET /companies/[invalidTicker] returns actual HTTP 404, not 200", async () => {
    const response = await fetch(`${BASE_URL}/companies/ZZZ-NOT-A-REAL-TICKER`);
    expect(response.status).toBe(404);
    const body = await response.text();
    expect(body).toContain("Page not found");
  });

  it("GET /comparisons/[validComparisonId] returns 200", async () => {
    const response = await fetch(`${BASE_URL}/comparisons/${validComparisonId}`);
    expect(response.status).toBe(200);
  });

  it("GET /comparisons/[invalidComparisonId] returns actual HTTP 404, not 200", async () => {
    const response = await fetch(`${BASE_URL}/comparisons/${invalidUuid}`);
    expect(response.status).toBe(404);
  });

  it("GET /comparisons/[validComparisonId]/evidence returns 200", async () => {
    const response = await fetch(`${BASE_URL}/comparisons/${validComparisonId}/evidence`);
    expect(response.status).toBe(200);
  });

  it("GET /comparisons/[invalidComparisonId]/evidence returns actual HTTP 404, not 200", async () => {
    const response = await fetch(`${BASE_URL}/comparisons/${invalidUuid}/evidence`);
    expect(response.status).toBe(404);
  });

  it("GET /passages/[validPassageComparisonId] returns 200", async () => {
    const response = await fetch(`${BASE_URL}/passages/${validPassageComparisonId}`);
    expect(response.status).toBe(200);
  });

  it("GET /passages/[invalidPassageComparisonId] returns actual HTTP 404, not 200", async () => {
    const response = await fetch(`${BASE_URL}/passages/${invalidUuid}`);
    expect(response.status).toBe(404);
    const body = await response.text();
    expect(body).toContain("Page not found");
  });
});
