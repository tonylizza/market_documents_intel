/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { CompanyCardSummary, DiscoveryItemSummary } from "@/lib/domain/comparison";
import type { ApplicationDataSummary } from "@/lib/domain/metric";

function makeCard(ticker: string): CompanyCardSummary {
  return {
    companyId: ticker,
    ticker,
    name: `${ticker} Test Company`,
    sector: null,
    firstReportPeriodEnd: "2016-06-30",
    latestReportPeriodEnd: "2024-06-30",
    reportCount: 5,
    comparisonCount: 4,
    isHistoricalPeak: false,
    latestComparison: {
      id: `${ticker}-cmp-1`,
      companyId: ticker,
      earlierPeriodEnd: "2023-06-30",
      laterPeriodEnd: "2024-06-30",
      gapMonths: 12,
      isTransition: false,
      isIrregularGap: false,
      isLatestForCompany: true,
      isHistoricalPeakChange: false,
      disclosureChangeScore: 0.4,
      disclosureChangeLabel: "Moderate change",
      disclosureChangePercentile: 60,
      disclosureChangeQuality: "NEEDS_REVIEW",
      disclosureChangeQualityLabel: "Review recommended",
      disclosureChangePrimaryEligible: false,
      disclosureChangeWarning: null,
      netToneChange: null,
      netToneChangeLabel: null,
      uncertaintyChange: null,
      uncertaintyChangeLabel: null,
      riskIntroductionRate: null,
      riskIntroductionLabel: null,
      riskRemovalRate: null,
      riskRemovalLabel: null,
      governanceChange: null,
      governanceChangeLabel: null,
      financialConditionChange: null,
      financialConditionChangeLabel: null,
      reportSideQuality: "GOOD",
      reportSideQualityLabel: "Analysis ready",
      reportSidePrimaryEligible: true,
      alignmentChangeQuality: "USABLE",
      alignmentChangeQualityLabel: "Usable attribution",
      alignmentChangePrimaryEligible: true,
      primaryFindingKey: null,
      secondaryFindingKey: null,
      tertiaryFindingKey: null,
      findingPayload: null,
    },
  };
}

const TICKERS = ["ACT", "BEL", "KP2", "SBP", "SDL", "SUR"];

const SUMMARY: ApplicationDataSummary = {
  companyCount: 6,
  reportCount: 30,
  comparisonCount: 25,
  earliestPeriodEnd: "2016-06-30",
  latestPeriodEnd: "2025-12-31",
  publicationNote: "Data reflects the currently active publication.",
};

const DISCOVERY_ITEMS: DiscoveryItemSummary[] = [
  {
    id: "d1",
    companyId: "ACT",
    companyTicker: "ACT",
    companyName: "ACT Test Company",
    reportComparisonId: "ACT-cmp-1",
    discoveryType: "largest_uncertainty_increase",
    rank: 1,
    percentile: 90,
    supportingValue: 1.5,
    supportingUnit: "rate_per_1000_words",
    qualityLabel: "Analysis ready",
  },
];

vi.mock("@/lib/repositories/postgres-company-repository", () => ({
  PostgresCompanyRepository: class {
    async listCompanies() {
      return [];
    }
    async getCompanyCardSummaries() {
      return TICKERS.map(makeCard);
    }
    async getLatestComparisonSummaries() {
      return DISCOVERY_ITEMS;
    }
    async getApplicationDataSummary() {
      return SUMMARY;
    }
  },
  LANGUAGE_DISCOVERY_TYPES: [
    "largest_uncertainty_increase",
    "largest_negative_tone_shift",
    "largest_risk_introduction",
    "largest_risk_removal",
    "largest_governance_shift",
    "largest_financial_condition_shift",
  ],
}));

const { default: CompaniesHomePage } = await import("@/app/(home)/page");

describe("Companies home page", () => {
  it("renders the product introduction", async () => {
    render(await CompaniesHomePage());
    expect(screen.getByRole("heading", { name: "Disclosure Change Intelligence" })).toBeInTheDocument();
    expect(screen.getByText(/Explore how corporate disclosures change over time/)).toBeInTheDocument();
  });

  it("renders the corpus summary", async () => {
    render(await CompaniesHomePage());
    expect(screen.getByText("30")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
  });

  it("renders exactly six company cards", async () => {
    render(await CompaniesHomePage());
    // Scoped to company-name headings specifically -- the latest-signals
    // section also renders its own (non-company) h3 titles.
    const headings = screen.getAllByRole("heading", { level: 3, name: /Test Company$/ });
    expect(headings).toHaveLength(6);
  });

  it("shows the disclosure-change magnitude with its quality label together", async () => {
    render(await CompaniesHomePage());
    expect(screen.getAllByText("Moderate change").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Review recommended").length).toBeGreaterThan(0);
  });

  it("never renders a largest-overall-change or new-disclosure-share ranking section", async () => {
    render(await CompaniesHomePage());
    expect(screen.queryByText(/largest overall change/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/new disclosure share/i)).not.toBeInTheDocument();
  });

  it("links to the methodology page", async () => {
    render(await CompaniesHomePage());
    expect(screen.getByRole("link", { name: /Read the methodology/ })).toHaveAttribute("href", "/methodology");
  });
});
