/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Company } from "@/lib/domain/company";
import type { CompanyCardSummary, DiscoveryItemSummary } from "@/lib/domain/comparison";
import type { ApplicationDataSummary } from "@/lib/domain/metric";
import type { DiscoveryItem } from "@/lib/domain/discovery";
import type { DiscoveryType } from "@/lib/config/discovery";

let mockAvailableTypes: DiscoveryType[] = ["largest_risk_introduction", "largest_uncertainty_increase"];
let mockItems: DiscoveryItem[] = [
  {
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
  },
];
let mockShouldThrow = false;

vi.mock("@/lib/repositories/postgres-company-repository", () => ({
  PostgresCompanyRepository: class {
    async listCompanies() {
      return [{ id: "c1", ticker: "ACT", name: "Acme Corp", sector: null, description: null, firstReportPeriodEnd: null, latestReportPeriodEnd: null, reportCount: 1, comparisonCount: 0, latestComparisonId: null, historicalPeakComparisonId: null, displayOrder: 0, hasCurrentData: true }] as Company[];
    }
    async getCompanyCardSummaries() {
      return [] as CompanyCardSummary[];
    }
    async getLatestComparisonSummaries() {
      return [] as DiscoveryItemSummary[];
    }
    async getApplicationDataSummary() {
      if (mockShouldThrow) throw new Error("connection refused");
      return { companyCount: 6, reportCount: 30, comparisonCount: 25, earliestPeriodEnd: "2016-06-30", latestPeriodEnd: "2024-06-30", publicationNote: "" } satisfies ApplicationDataSummary;
    }
  },
}));

vi.mock("@/lib/repositories/postgres-discovery-repository", () => ({
  PostgresDiscoveryRepository: class {
    async listAvailableDiscoveryTypes() {
      if (mockShouldThrow) throw new Error("connection refused");
      return mockAvailableTypes;
    }
    async getDiscoveryItems() {
      return mockItems;
    }
  },
}));

const { default: DiscoverPage } = await import("@/app/discover/page");

describe("DiscoverPage", () => {
  it("renders filters and results for the default (first available) ranking", async () => {
    mockAvailableTypes = ["largest_risk_introduction", "largest_uncertainty_increase"];
    mockItems = [mockItems[0]];
    mockShouldThrow = false;
    const jsx = await DiscoverPage({ searchParams: Promise.resolve({}) });
    render(jsx);
    expect(screen.getByLabelText("Ranking")).toBeInTheDocument();
    expect(screen.getAllByText("Acme Corp (ACT)").length).toBeGreaterThan(0);
  });

  it("does not show the largest_overall_change/largest_new_disclosure_share tabs when they have zero items", async () => {
    mockAvailableTypes = ["largest_risk_introduction"];
    const jsx = await DiscoverPage({ searchParams: Promise.resolve({}) });
    render(jsx);
    expect(screen.queryByRole("option", { name: /overall disclosure change/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /new-disclosure share/i })).not.toBeInTheDocument();
  });

  it("renders a restrained empty state when there are no discovery items at all", async () => {
    mockAvailableTypes = [];
    const jsx = await DiscoverPage({ searchParams: Promise.resolve({}) });
    render(jsx);
    expect(screen.getByText(/No discovery rankings are currently available/)).toBeInTheDocument();
  });

  it("explains category-specific ranking semantics on the page", async () => {
    mockAvailableTypes = ["largest_risk_introduction"];
    const jsx = await DiscoverPage({ searchParams: Promise.resolve({}) });
    render(jsx);
    expect(screen.getAllByText(/category-specific/).length).toBeGreaterThan(0);
  });

  it("renders a safe error state when the database is unavailable", async () => {
    mockShouldThrow = true;
    const jsx = await DiscoverPage({ searchParams: Promise.resolve({}) });
    render(jsx);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    mockShouldThrow = false;
  });
});
