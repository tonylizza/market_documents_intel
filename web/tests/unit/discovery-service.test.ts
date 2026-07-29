import { describe, expect, it } from "vitest";
import {
  filterDiscoveryItemsByMinQuality,
  getDiscoveryPageViewModel,
  resolveMinQualityParam,
  resolvePeriodDateParam,
  resolveSelectedDiscoveryType,
} from "@/lib/services/discovery-service";
import type { CompanyRepository } from "@/lib/repositories/company-repository";
import type { DiscoveryRepository } from "@/lib/repositories/discovery-repository";
import type { Company, CompanyDetail, CompanyHistory } from "@/lib/domain/company";
import type { CompanyCardSummary, DiscoveryItemSummary } from "@/lib/domain/comparison";
import type { ApplicationDataSummary } from "@/lib/domain/metric";
import type { DiscoveryItem } from "@/lib/domain/discovery";
import type { DiscoveryType } from "@/lib/config/discovery";

function makeItem(overrides: Partial<DiscoveryItem> = {}): DiscoveryItem {
  return {
    id: "d1",
    discoveryType: "largest_risk_introduction",
    rankScope: "corpus",
    rank: 1,
    percentile: 90,
    companyId: "c1",
    companyTicker: "ACT",
    companyName: "Acme Corp",
    reportComparisonId: "cmp-1",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    findingHeadline: "Risk language introduced",
    supportingValue: 2.1,
    supportingValueDisplay: "+2.10 / 1,000 words",
    supportingUnit: "rate_per_1000_words",
    qualityLabel: "Strong attribution",
    ...overrides,
  };
}

function makeCompanyRepository(overrides: Partial<CompanyRepository> = {}): CompanyRepository {
  return {
    listCompanies: async () => [] as Company[],
    getCompanyCardSummaries: async () => [] as CompanyCardSummary[],
    getLatestComparisonSummaries: async () => [] as DiscoveryItemSummary[],
    getApplicationDataSummary: async () =>
      ({ companyCount: 6, reportCount: 30, comparisonCount: 25, earliestPeriodEnd: "2016-06-30", latestPeriodEnd: "2024-06-30", publicationNote: "" }) satisfies ApplicationDataSummary,
    getCompanyByTicker: async () => null as CompanyDetail | null,
    getCompanyHistory: async () => null as CompanyHistory | null,
    ...overrides,
  };
}

function makeDiscoveryRepository(overrides: Partial<DiscoveryRepository> = {}): DiscoveryRepository {
  return {
    listAvailableDiscoveryTypes: async () => ["largest_risk_introduction", "largest_risk_removal"] as DiscoveryType[],
    getDiscoveryItems: async () => [makeItem()],
    ...overrides,
  };
}

describe("resolveSelectedDiscoveryType", () => {
  it("selects the requested type when it's valid and currently available", () => {
    expect(resolveSelectedDiscoveryType("largest_risk_removal", ["largest_risk_introduction", "largest_risk_removal"])).toBe(
      "largest_risk_removal",
    );
  });

  it("falls back to the first available type when the requested one is invalid", () => {
    expect(resolveSelectedDiscoveryType("not-a-type", ["largest_risk_introduction"])).toBe("largest_risk_introduction");
  });

  it("falls back to the first available type when the requested one is currently empty (unavailable)", () => {
    expect(resolveSelectedDiscoveryType("largest_overall_change", ["largest_risk_introduction"])).toBe(
      "largest_risk_introduction",
    );
  });

  it("returns null when there are no available types at all", () => {
    expect(resolveSelectedDiscoveryType("largest_risk_introduction", [])).toBeNull();
  });
});

describe("resolveMinQualityParam", () => {
  it("accepts a known raw quality tier", () => {
    expect(resolveMinQualityParam("GOOD")).toBe("GOOD");
  });

  it("returns null for an invalid/missing value", () => {
    expect(resolveMinQualityParam("bogus")).toBeNull();
    expect(resolveMinQualityParam(null)).toBeNull();
    expect(resolveMinQualityParam(undefined)).toBeNull();
  });
});

describe("resolvePeriodDateParam", () => {
  it("accepts a well-formed YYYY-MM-DD value", () => {
    expect(resolvePeriodDateParam("2024-06-30")).toBe("2024-06-30");
  });

  it("rejects a malformed or non-date query value, never passed unvalidated into SQL", () => {
    expect(resolvePeriodDateParam("not-a-date")).toBeNull();
    expect(resolvePeriodDateParam("2024-06-30T00:00:00Z")).toBeNull();
    expect(resolvePeriodDateParam("'; DROP TABLE app.report_comparisons; --")).toBeNull();
  });

  it("returns null for a missing value", () => {
    expect(resolvePeriodDateParam(null)).toBeNull();
    expect(resolvePeriodDateParam(undefined)).toBeNull();
  });
});

describe("filterDiscoveryItemsByMinQuality", () => {
  it("returns all items unfiltered when no minimum is set", () => {
    const items = [makeItem({ qualityLabel: "Attribution unavailable" })];
    expect(filterDiscoveryItemsByMinQuality(items, "alignment-change", null)).toHaveLength(1);
  });

  it("keeps an item at or above the minimum using the ranking's own quality dimension", () => {
    const items = [makeItem({ qualityLabel: "Strong attribution" })];
    expect(filterDiscoveryItemsByMinQuality(items, "alignment-change", "USABLE")).toHaveLength(1);
  });

  it("excludes an item below the minimum", () => {
    const items = [makeItem({ qualityLabel: "Attribution uncertain" })];
    expect(filterDiscoveryItemsByMinQuality(items, "alignment-change", "GOOD")).toHaveLength(0);
  });

  it("never matches a label from the wrong quality dimension's vocabulary", () => {
    // "Analysis ready" is report-side vocabulary, not alignment-change --
    // resolving it against alignment-change must fail to match and so be
    // excluded, never silently treated as GOOD.
    const items = [makeItem({ qualityLabel: "Analysis ready" })];
    expect(filterDiscoveryItemsByMinQuality(items, "alignment-change", "GOOD")).toHaveLength(0);
  });
});

describe("getDiscoveryPageViewModel", () => {
  it("uses the first available type when none is requested", async () => {
    const viewModel = await getDiscoveryPageViewModel(makeDiscoveryRepository(), makeCompanyRepository(), {});
    expect(viewModel.selectedType).toBe("largest_risk_introduction");
    expect(viewModel.items).toHaveLength(1);
  });

  it("carries filter options from the company repository (companies + period range), no duplicate query", async () => {
    const companyRepository = makeCompanyRepository({
      listCompanies: async () => [{ id: "c1", ticker: "ACT", name: "Acme Corp", sector: null, description: null, firstReportPeriodEnd: null, latestReportPeriodEnd: null, reportCount: 1, comparisonCount: 0, latestComparisonId: null, historicalPeakComparisonId: null, displayOrder: 0, hasCurrentData: true }],
    });
    const viewModel = await getDiscoveryPageViewModel(makeDiscoveryRepository(), companyRepository, {});
    expect(viewModel.filterOptions.companies).toEqual([{ ticker: "ACT", name: "Acme Corp" }]);
    expect(viewModel.filterOptions.earliestPeriodEnd).toBe("2016-06-30");
  });

  it("returns an empty availableTypes list and empty items when the corpus has no discovery items at all", async () => {
    const viewModel = await getDiscoveryPageViewModel(
      makeDiscoveryRepository({ listAvailableDiscoveryTypes: async () => [] }),
      makeCompanyRepository(),
      {},
    );
    expect(viewModel.availableTypes).toEqual([]);
    expect(viewModel.items).toEqual([]);
  });

  it("applies the minQuality filter from params to the fetched items", async () => {
    const discoveryRepository = makeDiscoveryRepository({
      getDiscoveryItems: async () => [makeItem({ qualityLabel: "Attribution uncertain" })],
    });
    const viewModel = await getDiscoveryPageViewModel(discoveryRepository, makeCompanyRepository(), {
      type: "largest_risk_introduction",
      minQuality: "GOOD",
    });
    expect(viewModel.items).toEqual([]);
  });
});
