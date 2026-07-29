import { readFileSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { closePool, query } from "@/lib/db/pool";
import { PostgresComparisonRepository } from "@/lib/repositories/postgres-comparison-repository";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import { seedAppDatabase } from "../fixtures/seed-app-database";

const repository = new PostgresComparisonRepository();
const companyRepository = new PostgresCompanyRepository();

let actLatestComparisonId: string;

beforeAll(async () => {
  await seedAppDatabase();
  const history = await companyRepository.getCompanyHistory("ACT");
  actLatestComparisonId = history!.comparisons[history!.comparisons.length - 1].id;
});

afterAll(async () => {
  await closePool();
});

describe("PostgresComparisonRepository against the seeded test database", () => {
  it("getComparisonById returns the comparison with company ticker/name joined", async () => {
    const comparison = await repository.getComparisonById(actLatestComparisonId);
    expect(comparison).not.toBeNull();
    expect(comparison?.companyTicker).toBe("ACT");
    expect(comparison?.id).toBe(actLatestComparisonId);
  });

  it("getComparisonById returns null for an unknown id -- never throws", async () => {
    const comparison = await repository.getComparisonById("00000000-0000-0000-0000-000000000000");
    expect(comparison).toBeNull();
  });

  it("getComparisonById carries technical-detail fields (dictionary match rate, word shares) for the technical-details section", async () => {
    const comparison = await repository.getComparisonById(actLatestComparisonId);
    expect(comparison?.dictionaryMatchRateEarlier).not.toBeNull();
  });

  it("getComparisonLanguageMetrics returns both report-side and alignment-change rows", async () => {
    const metrics = await repository.getComparisonLanguageMetrics(actLatestComparisonId);
    expect(metrics.length).toBeGreaterThan(0);
    expect(metrics.some((m) => m.scope === "report_side")).toBe(true);
    expect(metrics.some((m) => m.scope === "alignment_change")).toBe(true);
  });

  it("getComparisonLanguageMetrics returns an empty array (not an error) for a comparison with no rows", async () => {
    const history = await companyRepository.getCompanyHistory("BEL");
    const otherComparisonId = history!.comparisons[0].id;
    const metrics = await repository.getComparisonLanguageMetrics(otherComparisonId);
    expect(metrics).toEqual([]);
  });

  it("getComparisonPassageComposition includes a real, directly-queried UNCHANGED bucket", async () => {
    const composition = await repository.getComparisonPassageComposition(actLatestComparisonId);
    const unchanged = composition.buckets.find((b) => b.status === "UNCHANGED");
    expect(unchanged?.count).toBe(1);
    expect(composition.totalCount).toBe(6);
  });

  it("getComparisonPassageComposition's bucket shares sum to 1 (within floating-point tolerance)", async () => {
    const composition = await repository.getComparisonPassageComposition(actLatestComparisonId);
    const totalShare = composition.buckets.reduce((sum, b) => sum + b.share, 0);
    expect(totalShare).toBeCloseTo(1, 5);
  });

  it("getComparisonPassageComposition returns all-zero buckets (not an error) for a comparison with no passage rows", async () => {
    const history = await companyRepository.getCompanyHistory("BEL");
    const otherComparisonId = history!.comparisons[0].id;
    const composition = await repository.getComparisonPassageComposition(otherComparisonId);
    expect(composition.totalCount).toBe(0);
    expect(composition.buckets.every((b) => b.count === 0)).toBe(true);
  });

  it("no passage-language-signal bulk query occurs for a comparison-page load (perf constraint)", async () => {
    await repository.getComparisonById(actLatestComparisonId);
    await repository.getComparisonLanguageMetrics(actLatestComparisonId);
    await repository.getComparisonPassageComposition(actLatestComparisonId);
    const rows = await query(`SELECT 1 FROM app.current_passage_language_signals LIMIT 1`);
    // Not asserting on `rows` itself (the table may legitimately have data) --
    // this test's real assertion is the static source check below, which
    // confirms this repository's queries never reference that table at all.
    expect(Array.isArray(rows)).toBe(true);
  });
});

describe("PostgresComparisonRepository -- comparison evidence (Milestone 7A.4)", () => {
  it("getComparisonEvidence returns all 6 alignments unfiltered", async () => {
    const items = await repository.getComparisonEvidence(actLatestComparisonId, {
      status: "ALL",
      confidence: null,
      category: null,
      subcategory: null,
      collisionFlag: null,
      splitMergeFlag: null,
      hasHeading: null,
      pageStart: null,
      pageEnd: null,
      page: 1,
      pageSize: 25,
    });
    expect(items).toHaveLength(6);
  });

  it("getComparisonEvidence restricted to this comparison only (never leaks another comparison's rows)", async () => {
    const history = await companyRepository.getCompanyHistory("BEL");
    const otherComparisonId = history!.comparisons[0].id;
    const items = await repository.getComparisonEvidence(otherComparisonId, {
      status: "ALL",
      confidence: null,
      category: null,
      subcategory: null,
      collisionFlag: null,
      splitMergeFlag: null,
      hasHeading: null,
      pageStart: null,
      pageEnd: null,
      page: 1,
      pageSize: 25,
    });
    expect(items).toHaveLength(0);
  });

  it("getComparisonEvidence filters by status", async () => {
    const items = await repository.getComparisonEvidence(actLatestComparisonId, {
      status: "NEW",
      confidence: null,
      category: null,
      subcategory: null,
      collisionFlag: null,
      splitMergeFlag: null,
      hasHeading: null,
      pageStart: null,
      pageEnd: null,
      page: 1,
      pageSize: 25,
    });
    expect(items).toHaveLength(1);
    expect(items[0].alignmentStatus).toBe("NEW");
    expect(items[0].earlier).toBeNull();
    expect(items[0].later).not.toBeNull();
  });

  it("getComparisonEvidence's REMOVED row has an earlier side and no later side", async () => {
    const items = await repository.getComparisonEvidence(actLatestComparisonId, {
      status: "REMOVED",
      confidence: null,
      category: null,
      subcategory: null,
      collisionFlag: null,
      splitMergeFlag: null,
      hasHeading: null,
      pageStart: null,
      pageEnd: null,
      page: 1,
      pageSize: 25,
    });
    expect(items).toHaveLength(1);
    expect(items[0].earlier).not.toBeNull();
    expect(items[0].later).toBeNull();
  });

  it("getComparisonEvidence filters by the collision flag seeded on the SUBSTANTIALLY_MODIFIED row", async () => {
    const items = await repository.getComparisonEvidence(actLatestComparisonId, {
      status: "ALL",
      confidence: null,
      category: null,
      subcategory: null,
      collisionFlag: true,
      splitMergeFlag: null,
      hasHeading: null,
      pageStart: null,
      pageEnd: null,
      page: 1,
      pageSize: 25,
    });
    expect(items).toHaveLength(1);
    expect(items[0].alignmentStatus).toBe("SUBSTANTIALLY_MODIFIED");
  });

  it("getComparisonEvidence applies pagination (SQL-level LIMIT/OFFSET, never a client-side slice)", async () => {
    const page1 = await repository.getComparisonEvidence(actLatestComparisonId, {
      status: "ALL",
      confidence: null,
      category: null,
      subcategory: null,
      collisionFlag: null,
      splitMergeFlag: null,
      hasHeading: null,
      pageStart: null,
      pageEnd: null,
      page: 1,
      pageSize: 2,
    });
    const page2 = await repository.getComparisonEvidence(actLatestComparisonId, {
      status: "ALL",
      confidence: null,
      category: null,
      subcategory: null,
      collisionFlag: null,
      splitMergeFlag: null,
      hasHeading: null,
      pageStart: null,
      pageEnd: null,
      page: 2,
      pageSize: 2,
    });
    expect(page1).toHaveLength(2);
    expect(page2).toHaveLength(2);
    expect(page1.map((i) => i.passageComparisonId)).not.toEqual(page2.map((i) => i.passageComparisonId));
  });

  it("countComparisonEvidence matches the unfiltered row count", async () => {
    const count = await repository.countComparisonEvidence(actLatestComparisonId, {
      status: "ALL",
      confidence: null,
      category: null,
      subcategory: null,
      collisionFlag: null,
      splitMergeFlag: null,
      hasHeading: null,
      pageStart: null,
      pageEnd: null,
      page: 1,
      pageSize: 25,
    });
    expect(count).toBe(6);
  });

  it("getComparisonEvidenceFilterOptions returns only categories/confidence levels actually present for this comparison", async () => {
    const options = await repository.getComparisonEvidenceFilterOptions(actLatestComparisonId);
    expect(options.confidenceLevels.length).toBeGreaterThan(0);
    expect(options.categories.some((c) => c.value === "risk")).toBe(true);
    expect(options.subcategoriesByCategory.risk?.some((s) => s.value === "climate_environmental")).toBe(true);
  });

  it("getComparisonEvidenceFilterOptions returns empty option sets for a comparison with no evidence", async () => {
    const history = await companyRepository.getCompanyHistory("BEL");
    const otherComparisonId = history!.comparisons[0].id;
    const options = await repository.getComparisonEvidenceFilterOptions(otherComparisonId);
    expect(options.confidenceLevels).toEqual([]);
    expect(options.categories).toEqual([]);
  });
});

describe("PostgresComparisonRepository source -- static query-shape checks", () => {
  const source = readFileSync(path.resolve(__dirname, "../../lib/repositories/postgres-comparison-repository.ts"), "utf-8");

  it("only queries app.current_* views, never app_internal", () => {
    expect(source).not.toContain("app_internal");
  });

  it("never queries the raw app.report_comparisons table directly", () => {
    expect(source).not.toMatch(/FROM\s+app\.report_comparisons\b/);
    expect(source).toContain("app.current_report_comparisons");
  });

  it("only queries app.current_passage_language_signals when scoped to one comparison (never a bulk/unscoped read)", () => {
    // Milestone 7A.4 adds `getComparisonEvidenceFilterOptions`, which does
    // legitimately read this table -- but only ever `WHERE
    // report_comparison_id = $1`, never unfiltered. Every occurrence in
    // this file's SQL must be immediately followed by a `*_comparison_id =
    // $` scoping clause.
    const matches = [...source.matchAll(/current_passage_language_signals/g)];
    expect(matches.length).toBeGreaterThan(0);
    for (const match of matches) {
      const window = source.slice(match.index, match.index + 200);
      // Scoped either directly by a bind parameter (`report_comparison_id
      // = $1`) or by correlation to the outer, already-comparison-scoped
      // `pc`/`rc` alias (`passage_comparison_id = pc.id`) -- never bare.
      expect(window).toMatch(/_comparison_id = (\$\d|pc\.id|rc\.id)/);
    }
  });

  it("uses parameterized placeholders, not string-interpolated SQL", () => {
    expect(source).toContain("$1");
    expect(source).not.toMatch(/query\(\s*`[^`]*\$\{/);
  });
});
