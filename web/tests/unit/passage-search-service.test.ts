import { describe, expect, it } from "vitest";
import { buildPassageSearchViewModel } from "@/lib/services/passage-search-service";
import { parsePassageSearchParams } from "@/lib/services/passage-search-params";
import type { PassageRepository } from "@/lib/repositories/passage-repository";
import type { PassageFilterOptions, PassageSearchResult } from "@/lib/domain/passage";

const EMPTY_FILTER_OPTIONS: PassageFilterOptions = {
  companies: [{ value: "ACT", label: "Acme (ACT)" }],
  alignmentStatuses: [],
  confidenceLevels: [],
  passageTypes: [],
  categories: [],
  subcategoriesByCategory: {},
  reportSideQualities: [],
  alignmentChangeQualities: [],
};

function makeResult(overrides: Partial<PassageSearchResult> = {}): PassageSearchResult {
  return {
    passageId: "p1",
    passageComparisonId: "pc1",
    reportComparisonId: "rc1",
    companyId: "c1",
    companyTicker: "ACT",
    companyName: "Acme",
    reportId: "r1",
    reportPeriodEnd: "2024-06-30",
    reportSide: "LATER",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    heading: "Liquidity and going concern",
    headingHighlight: null,
    passageType: "HEADING_WITH_BODY",
    structuredContentCategory: null,
    firstPageNumber: 10,
    lastPageNumber: 10,
    wordCount: 40,
    primaryNarrativeEligible: true,
    featureEligible: true,
    excerpt: [{ text: "The group maintains adequate liquidity headroom throughout the year.", matched: false }],
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    confidenceLabel: "High confidence",
    collisionFlag: false,
    splitMergeFlag: false,
    rank: 0.5,
    ...overrides,
  };
}

function makeFakeRepository(overrides: Partial<PassageRepository> = {}): PassageRepository {
  return {
    searchPassages: async () => [makeResult()],
    countPassageSearchResults: async () => ({ count: 1, capped: false }),
    getPassageFilterOptions: async () => EMPTY_FILTER_OPTIONS,
    getPassageComparisonById: async () => null,
    getPassageLanguageSignals: async () => [],
    ...overrides,
  };
}

describe("buildPassageSearchViewModel", () => {
  it("returns an empty page and never calls searchPassages/count when there is no searchable input", async () => {
    let searchCalled = false;
    let countCalled = false;
    const repository = makeFakeRepository({
      searchPassages: async () => {
        searchCalled = true;
        return [];
      },
      countPassageSearchResults: async () => {
        countCalled = true;
        return { count: 0, capped: false };
      },
    });
    const { page, filterOptions } = await buildPassageSearchViewModel(repository, parsePassageSearchParams({}));
    expect(page.results).toEqual([]);
    expect(page.pagination.totalCount).toBe(0);
    expect(searchCalled).toBe(false);
    expect(countCalled).toBe(false);
    expect(filterOptions.companies).toHaveLength(1);
  });

  it("runs the search and count queries when a query is present", async () => {
    const repository = makeFakeRepository();
    const { page } = await buildPassageSearchViewModel(repository, parsePassageSearchParams({ q: "liquidity" }));
    expect(page.results).toHaveLength(1);
    expect(page.pagination.totalCount).toBe(1);
  });

  it("highlights the excerpt and heading against the search terms", async () => {
    const repository = makeFakeRepository();
    const { page } = await buildPassageSearchViewModel(repository, parsePassageSearchParams({ q: "liquidity" }));
    const result = page.results[0];
    expect(result.headingHighlight?.some((s) => s.matched && s.text.toLowerCase() === "liquidity")).toBe(true);
    expect(result.excerpt.some((s) => s.matched && s.text.toLowerCase() === "liquidity")).toBe(true);
  });

  it("does not highlight anything when searching by filters only (no query)", async () => {
    const repository = makeFakeRepository();
    const { page } = await buildPassageSearchViewModel(repository, parsePassageSearchParams({ company: "ACT" }));
    const result = page.results[0];
    expect(result.excerpt.every((s) => !s.matched)).toBe(true);
    expect(result.headingHighlight?.every((s) => !s.matched)).toBe(true);
  });

  it("marks the page as capped and reports the capped count", async () => {
    const repository = makeFakeRepository({ countPassageSearchResults: async () => ({ count: 1000, capped: true }) });
    const { page } = await buildPassageSearchViewModel(repository, parsePassageSearchParams({ q: "liquidity" }));
    expect(page.pagination.totalIsCapped).toBe(true);
    expect(page.pagination.totalCount).toBe(1000);
  });

  it("handles a report-only passage (no passageComparisonId) gracefully", async () => {
    const repository = makeFakeRepository({
      searchPassages: async () => [
        makeResult({ passageComparisonId: null, reportComparisonId: null, alignmentStatus: null, confidence: null, confidenceLabel: null }),
      ],
    });
    const { page } = await buildPassageSearchViewModel(repository, parsePassageSearchParams({ q: "liquidity" }));
    expect(page.results[0].passageComparisonId).toBeNull();
    expect(page.results[0].alignmentStatus).toBeNull();
  });
});
