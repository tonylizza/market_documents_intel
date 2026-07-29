import { readFileSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { closePool } from "@/lib/db/pool";
import { PostgresDiscoveryRepository } from "@/lib/repositories/postgres-discovery-repository";
import { seedAppDatabase } from "../fixtures/seed-app-database";

const repository = new PostgresDiscoveryRepository();

beforeAll(async () => {
  await seedAppDatabase();
});

afterAll(async () => {
  await closePool();
});

describe("PostgresDiscoveryRepository against the seeded test database", () => {
  it("listAvailableDiscoveryTypes returns only types with real rows, never the full 8-type list unconditionally", async () => {
    const types = await repository.listAvailableDiscoveryTypes();
    expect(types).toContain("largest_uncertainty_increase");
    expect(types).toContain("largest_risk_introduction");
    expect(types).not.toContain("largest_overall_change");
    expect(types).not.toContain("largest_new_disclosure_share");
  });

  it("getDiscoveryItems filters by discovery type and rank scope", async () => {
    const items = await repository.getDiscoveryItems({ type: "largest_uncertainty_increase", scope: "corpus" });
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      expect(item.discoveryType).toBe("largest_uncertainty_increase");
      expect(item.rankScope).toBe("corpus");
    }
  });

  it("getDiscoveryItems filters by company ticker", async () => {
    const items = await repository.getDiscoveryItems({
      type: "largest_uncertainty_increase",
      scope: "corpus",
      companyTicker: "ACT",
    });
    expect(items.length).toBeGreaterThan(0);
    expect(items.every((item) => item.companyTicker === "ACT")).toBe(true);
  });

  it("getDiscoveryItems returns an empty array for a company with no matching items", async () => {
    const items = await repository.getDiscoveryItems({
      type: "largest_uncertainty_increase",
      scope: "corpus",
      companyTicker: "NOPE",
    });
    expect(items).toEqual([]);
  });

  it("getDiscoveryItems resolves a finding headline via the finding-copy mapping, not the raw key", async () => {
    const items = await repository.getDiscoveryItems({ type: "largest_uncertainty_increase", scope: "corpus" });
    expect(items[0].findingHeadline).toBe("Uncertainty language increased");
  });

  it("getDiscoveryItems orders rows by rank, deterministically, never re-sorted by a rounded display value", async () => {
    const items = await repository.getDiscoveryItems({ type: "largest_uncertainty_increase", scope: "corpus" });
    for (let i = 1; i < items.length; i += 1) {
      expect(items[i].rank).toBeGreaterThanOrEqual(items[i - 1].rank);
    }
  });

  it("getDiscoveryItems filters by period range", async () => {
    const items = await repository.getDiscoveryItems({
      type: "largest_uncertainty_increase",
      scope: "corpus",
      periodStart: "2099-01-01",
    });
    expect(items).toEqual([]);
  });
});

describe("PostgresDiscoveryRepository source -- static query-shape checks", () => {
  const source = readFileSync(path.resolve(__dirname, "../../lib/repositories/postgres-discovery-repository.ts"), "utf-8");

  it("only queries app.current_* views, never app_internal", () => {
    expect(source).not.toContain("app_internal");
  });

  it("never queries the raw app.discovery_items table directly", () => {
    expect(source).not.toMatch(/FROM\s+app\.discovery_items\b/);
    expect(source).toContain("app.current_discovery_items");
  });

  it("uses parameterized placeholders, not string-interpolated SQL", () => {
    expect(source).toContain("$1");
    expect(source).not.toMatch(/query\(\s*`[^`]*\$\{/);
  });
});
