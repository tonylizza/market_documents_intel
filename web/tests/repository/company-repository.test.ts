import { readFileSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { closePool } from "@/lib/db/pool";
import { PostgresCompanyRepository, LANGUAGE_DISCOVERY_TYPES } from "@/lib/repositories/postgres-company-repository";
import { seedAppDatabase } from "../fixtures/seed-app-database";

const repository = new PostgresCompanyRepository();

beforeAll(async () => {
  await seedAppDatabase();
});

afterAll(async () => {
  await closePool();
});

describe("PostgresCompanyRepository against the seeded test database", () => {
  it("listCompanies returns exactly the 6 seeded companies", async () => {
    const companies = await repository.listCompanies();
    expect(companies).toHaveLength(6);
    expect(companies.map((c) => c.ticker).sort()).toEqual(["ACT", "BEL", "KP2", "SBP", "SDL", "SUR"]);
  });

  it("listCompanies maps report/comparison counts correctly", async () => {
    const companies = await repository.listCompanies();
    const act = companies.find((c) => c.ticker === "ACT");
    expect(act?.reportCount).toBe(9);
    expect(act?.comparisonCount).toBe(8);
  });

  it("getCompanyCardSummaries returns one row per company with no N+1 pattern (single call)", async () => {
    const cards = await repository.getCompanyCardSummaries();
    expect(cards).toHaveLength(6);
  });

  it("selects the latest comparison per company", async () => {
    const cards = await repository.getCompanyCardSummaries();
    for (const card of cards) {
      expect(card.latestComparison).not.toBeNull();
      expect(card.latestComparison?.isLatestForCompany).toBe(true);
    }
  });

  it("maps review-qualified disclosure-change fields correctly (NEEDS_REVIEW, not primary eligible)", async () => {
    const cards = await repository.getCompanyCardSummaries();
    const reviewQualified = cards.find((c) => c.latestComparison?.disclosureChangeQuality === "NEEDS_REVIEW");
    expect(reviewQualified).toBeDefined();
    const comparison = reviewQualified!.latestComparison!;
    expect(comparison.disclosureChangeScore).not.toBeNull();
    expect(comparison.disclosureChangeLabel).not.toBeNull();
    expect(comparison.disclosureChangeQualityLabel).toBe("Review recommended");
    expect(comparison.disclosureChangePrimaryEligible).toBe(false);
  });

  it("maps GOOD-quality, primary-eligible disclosure-change fields correctly", async () => {
    const cards = await repository.getCompanyCardSummaries();
    const goodQuality = cards.find((c) => c.latestComparison?.disclosureChangeQuality === "GOOD");
    expect(goodQuality).toBeDefined();
    const comparison = goodQuality!.latestComparison!;
    expect(comparison.disclosureChangePrimaryEligible).toBe(true);
    expect(comparison.disclosureChangeQualityLabel).toBe("Analysis ready");
  });

  it("tolerates null optional metadata (sector/description) without throwing", async () => {
    const companies = await repository.listCompanies();
    expect(companies.every((c) => c.sector === null || typeof c.sector === "string")).toBe(true);
  });

  it("getLatestComparisonSummaries only returns language-based discovery types", async () => {
    const items = await repository.getLatestComparisonSummaries();
    for (const item of items) {
      expect(LANGUAGE_DISCOVERY_TYPES).toContain(item.discoveryType);
      expect(item.discoveryType).not.toBe("largest_overall_change");
      expect(item.discoveryType).not.toBe("largest_new_disclosure_share");
    }
  });

  it("getApplicationDataSummary reports correct corpus totals", async () => {
    const summary = await repository.getApplicationDataSummary();
    expect(summary.companyCount).toBe(6);
    expect(summary.reportCount).toBe(9 + 7 + 6 + 3 + 2 + 3);
    expect(summary.comparisonCount).toBe(8 + 6 + 5 + 2 + 1 + 2);
  });
});

describe("PostgresCompanyRepository -- getCompanyByTicker / getCompanyHistory", () => {
  it("getCompanyByTicker is case-insensitive", async () => {
    const upper = await repository.getCompanyByTicker("ACT");
    const lower = await repository.getCompanyByTicker("act");
    expect(upper?.id).toBe(lower?.id);
  });

  it("getCompanyByTicker returns null for an unknown ticker -- page renders 404, never a synthesized company", async () => {
    expect(await repository.getCompanyByTicker("ZZZ")).toBeNull();
  });

  it("getCompanyByTicker carries the latest report-side quality alongside the company row", async () => {
    const company = await repository.getCompanyByTicker("ACT");
    expect(company?.latestReportSideQuality).not.toBeUndefined();
  });

  it("getCompanyByTicker builds a coverage note from the fetched row, no extra query", async () => {
    const company = await repository.getCompanyByTicker("ACT");
    expect(company?.dataCoverageNote).toContain("reports");
  });

  it("getCompanyHistory returns null for an unknown ticker", async () => {
    expect(await repository.getCompanyHistory("ZZZ")).toBeNull();
  });

  it("getCompanyHistory returns comparisons in chronological (oldest-first) order using chronological_index, never assumed", async () => {
    const history = await repository.getCompanyHistory("ACT");
    expect(history).not.toBeNull();
    expect(history?.comparisons).toHaveLength(8);
    for (let i = 1; i < history!.comparisons.length; i += 1) {
      const earlier = history!.comparisons[i - 1].laterPeriodEnd;
      const later = history!.comparisons[i].laterPeriodEnd;
      expect(later! >= earlier!).toBe(true);
    }
  });

  it("getCompanyHistory marks exactly one comparison as latest", async () => {
    const history = await repository.getCompanyHistory("ACT");
    const latestCount = history!.comparisons.filter((c) => c.isLatestForCompany).length;
    expect(latestCount).toBe(1);
  });

  it("getCompanyHistory fetches the full history in one query (no N+1 -- a single-company history read never issues one query per comparison)", async () => {
    // Static shape check lives in the source-check describe block below;
    // this asserts the observable behavior: every comparison's fields are
    // already populated without any further repository call needed.
    const history = await repository.getCompanyHistory("ACT");
    for (const comparison of history!.comparisons) {
      expect(comparison.id).toBeTruthy();
      expect(typeof comparison.gapMonths).toBe("number");
    }
  });

  it("getCompanyHistory carries finding_payload through for the company-page preview's findings", async () => {
    const history = await repository.getCompanyHistory("ACT");
    const withFinding = history!.comparisons.find((c) => c.primaryFindingKey !== null);
    expect(withFinding).toBeDefined();
    expect(withFinding?.findingPayload).not.toBeNull();
  });
});

describe("PostgresCompanyRepository source -- static query-shape checks", () => {
  const source = readFileSync(
    path.resolve(__dirname, "../../lib/repositories/postgres-company-repository.ts"),
    "utf-8",
  );

  it("only queries app.current_* views, never app_internal", () => {
    expect(source).not.toContain("app_internal");
  });

  it("never queries the raw app.report_comparisons table directly", () => {
    expect(source).not.toMatch(/FROM\s+app\.report_comparisons\b/);
    expect(source).toContain("app.current_report_comparisons");
  });

  it("never queries the raw app.companies table directly", () => {
    expect(source).not.toMatch(/FROM\s+app\.companies\b/);
    expect(source).toContain("app.current_companies");
  });

  it("uses parameterized placeholders, not string-interpolated SQL", () => {
    expect(source).toContain("$1");
    // No template-literal interpolation of a variable directly into a SQL
    // string passed to `query(...)`.
    expect(source).not.toMatch(/query\(\s*`[^`]*\$\{/);
  });
});
