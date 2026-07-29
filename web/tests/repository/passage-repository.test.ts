import { readFileSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { closePool, query } from "@/lib/db/pool";
import { PostgresPassageRepository } from "@/lib/repositories/postgres-passage-repository";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import { parsePassageSearchParams } from "@/lib/services/passage-search-params";
import { seedAppDatabase } from "../fixtures/seed-app-database";
import type { PassageSearchParams } from "@/lib/domain/passage";

const repository = new PostgresPassageRepository();
const companyRepository = new PostgresCompanyRepository();

let actLatestComparisonId: string;

function params(overrides: Partial<PassageSearchParams>): PassageSearchParams {
  return { ...parsePassageSearchParams({}), ...overrides };
}

beforeAll(async () => {
  await seedAppDatabase();
  const history = await companyRepository.getCompanyHistory("ACT");
  actLatestComparisonId = history!.comparisons[history!.comparisons.length - 1].id;
});

afterAll(async () => {
  await closePool();
});

describe("PostgresPassageRepository.searchPassages against the seeded test database", () => {
  it("finds the fixture passage by a lexical query (GIN full-text search)", async () => {
    const results = await repository.searchPassages(params({ query: "liquidity" }));
    expect(results.length).toBeGreaterThan(0);
    expect(results.some((r) => r.heading === "Liquidity and going concern")).toBe(true);
  });

  it("ranks a heading match at least as high as any body-only match (heading weight A > body weight B)", async () => {
    const results = await repository.searchPassages(params({ query: "liquidity", sort: "relevance" }));
    expect(results[0].rank).not.toBeNull();
    // relevance-sorted: the top result's rank must be >= every later result's rank.
    for (let i = 1; i < results.length; i += 1) {
      expect(results[0].rank!).toBeGreaterThanOrEqual(results[i].rank ?? 0);
    }
  });

  it("supports exact-phrase search", async () => {
    const results = await repository.searchPassages(params({ query: "going concern", exactPhrase: true }));
    expect(results.length).toBeGreaterThan(0);
  });

  it("never throws on malformed/adversarial query text (websearch_to_tsquery is forgiving)", async () => {
    await expect(repository.searchPassages(params({ query: "\"unterminated AND OR &&& (((" }))).resolves.not.toThrow();
  });

  it("filters by company", async () => {
    const results = await repository.searchPassages(params({ query: "liquidity", company: "ACT" }));
    expect(results.every((r) => r.companyTicker === "ACT")).toBe(true);
    const other = await repository.searchPassages(params({ query: "liquidity", company: "BEL" }));
    expect(other).toEqual([]);
  });

  it("filters by alignment status", async () => {
    const results = await repository.searchPassages(params({ company: "ACT", alignmentStatus: "NEW" }));
    expect(results).toHaveLength(1);
    expect(results[0].heading).toBe("New disclosure on climate risk");
    expect(results[0].reportSide).toBe("LATER");
  });

  it("filters by report side", async () => {
    const earlier = await repository.searchPassages(params({ company: "ACT", reportSide: "EARLIER" }));
    expect(earlier.every((r) => r.reportSide === "EARLIER")).toBe(true);
    const later = await repository.searchPassages(params({ company: "ACT", reportSide: "LATER" }));
    expect(later.every((r) => r.reportSide === "LATER")).toBe(true);
  });

  it("filters by collision flag (seeded true only on the SUBSTANTIALLY_MODIFIED alignment)", async () => {
    const results = await repository.searchPassages(params({ company: "ACT", collisionFlag: true }));
    expect(results.length).toBeGreaterThan(0);
    expect(results.every((r) => r.alignmentStatus === "SUBSTANTIALLY_MODIFIED")).toBe(true);
  });

  it("filters by financial-language category (via a scoped EXISTS against passage_language_signals)", async () => {
    const results = await repository.searchPassages(params({ category: "risk" }));
    expect(results.length).toBe(5);
  });

  it("filters by category + subcategory together", async () => {
    const results = await repository.searchPassages(params({ category: "risk", subcategory: "climate_environmental" }));
    expect(results.length).toBe(3);
    expect(results.every((r) => r.companyTicker === "ACT")).toBe(true);
  });

  it("returns a report-only passage with null alignment fields for a passage with no published alignment", async () => {
    // The fixture's "Directors' report" passage is deliberately never
    // referenced by any `passage_comparisons` row.
    const results = await repository.searchPassages(params({ query: "directors" }));
    expect(results.length).toBeGreaterThan(0);
    expect(results.every((r) => r.passageComparisonId === null && r.alignmentStatus === null)).toBe(true);
  });

  it("applies pagination in SQL (LIMIT/OFFSET), never a client-side slice", async () => {
    const page1 = await repository.searchPassages(params({ company: "ACT", pageSize: 2, page: 1 }));
    const page2 = await repository.searchPassages(params({ company: "ACT", pageSize: 2, page: 2 }));
    expect(page1).toHaveLength(2);
    expect(page2.length).toBeGreaterThan(0);
    expect(page1.map((r) => r.passageId)).not.toEqual(page2.map((r) => r.passageId));
  });

  it("produces a stable tie-break order (company filter run twice returns the same order)", async () => {
    const first = await repository.searchPassages(params({ company: "ACT", sort: "page_order" }));
    const second = await repository.searchPassages(params({ company: "ACT", sort: "page_order" }));
    expect(first.map((r) => r.passageId)).toEqual(second.map((r) => r.passageId));
  });
});

describe("PostgresPassageRepository.countPassageSearchResults", () => {
  it("matches the number of rows returned by an unbounded page size", async () => {
    const { count, capped } = await repository.countPassageSearchResults(params({ company: "ACT" }));
    expect(capped).toBe(false);
    const rows = await repository.searchPassages(params({ company: "ACT", pageSize: 50 }));
    expect(count).toBe(rows.length);
  });
});

describe("PostgresPassageRepository.getPassageFilterOptions", () => {
  it("returns the 6 real seeded companies", async () => {
    const options = await repository.getPassageFilterOptions();
    expect(options.companies).toHaveLength(6);
  });

  it("returns only alignment statuses/confidence levels/passage types actually present", async () => {
    const options = await repository.getPassageFilterOptions();
    expect(options.alignmentStatuses.length).toBeGreaterThan(0);
    expect(options.alignmentStatuses.every((s) => s.label !== s.value)).toBe(true);
    expect(options.confidenceLevels.length).toBeGreaterThan(0);
  });

  it("returns real category/subcategory combinations, not invented ones", async () => {
    const options = await repository.getPassageFilterOptions();
    expect(options.categories.some((c) => c.value === "risk")).toBe(true);
    expect(options.subcategoriesByCategory.risk?.some((s) => s.value === "climate_environmental")).toBe(true);
  });
});

describe("PostgresPassageRepository.getPassageComparisonById / getPassageLanguageSignals", () => {
  async function findPassageComparisonIdByStatus(status: string): Promise<string> {
    const rows = await query<{ id: string }>(
      `SELECT id FROM app.current_passage_comparisons WHERE report_comparison_id = $1 AND alignment_status = $2`,
      [actLatestComparisonId, status],
    );
    return rows[0].id;
  }

  it("returns null for an unknown passage comparison id -- never throws", async () => {
    expect(await repository.getPassageComparisonById("00000000-0000-0000-0000-000000000000")).toBeNull();
  });

  it("NEW: later side present, earlier side null", async () => {
    const id = await findPassageComparisonIdByStatus("NEW");
    const detail = await repository.getPassageComparisonById(id);
    expect(detail?.earlier).toBeNull();
    expect(detail?.later).not.toBeNull();
    expect(detail?.later?.heading).toBe("New disclosure on climate risk");
  });

  it("REMOVED: earlier side present, later side null", async () => {
    const id = await findPassageComparisonIdByStatus("REMOVED");
    const detail = await repository.getPassageComparisonById(id);
    expect(detail?.later).toBeNull();
    expect(detail?.earlier).not.toBeNull();
  });

  it("UNCHANGED: both sides present with full text", async () => {
    const id = await findPassageComparisonIdByStatus("UNCHANGED");
    const detail = await repository.getPassageComparisonById(id);
    expect(detail?.earlier?.text.length).toBeGreaterThan(0);
    expect(detail?.later?.text.length).toBeGreaterThan(0);
  });

  it("AMBIGUOUS (one-sided in this fixture): only the earlier side is present", async () => {
    const id = await findPassageComparisonIdByStatus("AMBIGUOUS");
    const detail = await repository.getPassageComparisonById(id);
    expect(detail?.earlier).not.toBeNull();
    expect(detail?.later).toBeNull();
  });

  it("a multi-page passage carries distinct first/last page numbers", async () => {
    const id = await findPassageComparisonIdByStatus("SUBSTANTIALLY_MODIFIED");
    const detail = await repository.getPassageComparisonById(id);
    expect(detail?.later?.firstPageNumber).toBe(40);
    expect(detail?.later?.lastPageNumber).toBe(41);
  });

  it("getPassageLanguageSignals returns only rows for the requested passage comparison (never a bulk read)", async () => {
    const id = await findPassageComparisonIdByStatus("UNCHANGED");
    const signals = await repository.getPassageLanguageSignals(id);
    expect(signals.length).toBeGreaterThan(0);
    expect(signals.some((s) => s.category === "risk" && s.subcategory === "liquidity" && s.isRetained)).toBe(true);
  });

  it("getPassageLanguageSignals returns an empty array (not an error) for an id with no signals", async () => {
    const history = await companyRepository.getCompanyHistory("BEL");
    const otherComparisonId = history!.comparisons[0].id;
    void otherComparisonId; // BEL has no passage_comparisons at all in this fixture
    const signals = await repository.getPassageLanguageSignals("00000000-0000-0000-0000-000000000000");
    expect(signals).toEqual([]);
  });
});

describe("PostgresPassageRepository source -- static query-shape checks", () => {
  const source = readFileSync(path.resolve(__dirname, "../../lib/repositories/postgres-passage-repository.ts"), "utf-8");

  it("only queries app.current_* views, never app_internal", () => {
    expect(source).not.toContain("app_internal");
  });

  it("never queries a raw (non-current_*) app publication table directly", () => {
    expect(source).not.toMatch(/FROM\s+app\.passages\b/);
    expect(source).not.toMatch(/FROM\s+app\.passage_comparisons\b/);
    expect(source).not.toMatch(/FROM\s+app\.passage_language_signals\b/);
  });

  it("never references a research-only table", () => {
    expect(source).not.toContain("market_documents.");
  });

  it("uses parameterized placeholders, never string-interpolated SQL inside a query() template literal", () => {
    expect(source).toContain("$1");
    expect(source).not.toMatch(/query\(\s*`[^`]*\$\{/);
    expect(source).not.toMatch(/query<[^>]*>\(\s*`[^`]*\$\{/);
  });

  it("uses the GIN-compatible search predicate (search_vector @@ websearch_to_tsquery)", () => {
    expect(source).toContain("search_vector @@ websearch_to_tsquery");
  });

  it("every sort key maps to a fixed, stable-tie-break SQL fragment (no arbitrary order-by string)", () => {
    expect(source).toContain("PASSAGE_SORT_SQL[params.sort]");
  });

  it("applies LIMIT/OFFSET in SQL, never fetching then slicing in TypeScript", () => {
    expect(source).toMatch(/LIMIT \$/);
    expect(source).not.toMatch(/\.slice\(offset/);
  });
});
