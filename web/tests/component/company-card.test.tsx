/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CompanyCard } from "@/components/CompanyCard";
import type { CompanyCardSummary } from "@/lib/domain/comparison";

function makeCard(overrides: Partial<CompanyCardSummary> = {}): CompanyCardSummary {
  return {
    companyId: "company-1",
    ticker: "ACT",
    name: "Acme Corp",
    sector: null,
    firstReportPeriodEnd: "2016-06-30",
    latestReportPeriodEnd: "2024-06-30",
    reportCount: 9,
    comparisonCount: 8,
    isHistoricalPeak: false,
    latestComparison: null,
    ...overrides,
  };
}

describe("CompanyCard", () => {
  it("renders company name, ticker, and report/comparison counts", () => {
    render(<CompanyCard company={makeCard()} />);
    expect(screen.getByRole("heading", { name: "Acme Corp" })).toBeInTheDocument();
    expect(screen.getByText("ACT")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("shows the disclosure-change magnitude label alongside its quality label -- never one without the other", () => {
    const card = makeCard({
      latestComparison: {
        id: "cmp-1",
        companyId: "company-1",
        earlierPeriodEnd: "2023-06-30",
        laterPeriodEnd: "2024-06-30",
        gapMonths: 12,
        isTransition: false,
        isIrregularGap: false,
        isLatestForCompany: true,
        isHistoricalPeakChange: false,
        disclosureChangeScore: 0.59,
        disclosureChangeLabel: "Notable change",
        disclosureChangePercentile: 80,
        disclosureChangeQuality: "NEEDS_REVIEW",
        disclosureChangeQualityLabel: "Review recommended",
        disclosureChangePrimaryEligible: false,
        disclosureChangeWarning: null,
        netToneChange: null,
        netToneChangeLabel: null,
        uncertaintyChange: null,
        uncertaintyChangeLabel: "Moderate increase",
        riskIntroductionRate: null,
        riskIntroductionLabel: "Notable increase",
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
    });
    render(<CompanyCard company={card} />);
    expect(screen.getByText("Notable change")).toBeInTheDocument();
    expect(screen.getByText("Review recommended")).toBeInTheDocument();
    expect(screen.getByText("Moderate increase")).toBeInTheDocument();
    expect(screen.getByText("Notable increase")).toBeInTheDocument();
  });

  it("renders a 'no comparison available' message when there is none", () => {
    render(<CompanyCard company={makeCard({ latestComparison: null })} />);
    expect(screen.getByText("No comparison available yet for this company.")).toBeInTheDocument();
  });

  it("shows the historical-peak indicator only when applicable", () => {
    const { rerender } = render(<CompanyCard company={makeCard({ isHistoricalPeak: false })} />);
    expect(screen.queryByText("Historical peak change")).not.toBeInTheDocument();

    rerender(<CompanyCard company={makeCard({ isHistoricalPeak: true })} />);
    expect(screen.getByText("Historical peak change")).toBeInTheDocument();
  });
});
