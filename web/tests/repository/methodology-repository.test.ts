import { readFileSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { closePool } from "@/lib/db/pool";
import { PostgresMethodologyRepository } from "@/lib/repositories/postgres-methodology-repository";
import { seedAppDatabase } from "../fixtures/seed-app-database";

const repository = new PostgresMethodologyRepository();

beforeAll(async () => {
  await seedAppDatabase();
});

afterAll(async () => {
  await closePool();
});

describe("PostgresMethodologyRepository against the seeded test database", () => {
  it("getMetricDefinitions returns the seeded metric catalog", async () => {
    const metrics = await repository.getMetricDefinitions();
    expect(metrics.length).toBeGreaterThan(0);
    expect(metrics.map((m) => m.metricKey)).toContain("disclosure_change_score");
  });

  it("getMetricDefinitions filters by the active publication_id, not an unfiltered scan", async () => {
    const source = readFileSync(
      path.resolve(__dirname, "../../lib/repositories/postgres-methodology-repository.ts"),
      "utf-8",
    );
    expect(source).toContain("WHERE publication_id = $1");
  });

  it("getMethodologyContentData combines metrics and corpus summary", async () => {
    const data = await repository.getMethodologyContentData();
    expect(data.metrics.length).toBeGreaterThan(0);
    expect(data.summary.companyCount).toBe(6);
  });
});
