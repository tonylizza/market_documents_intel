/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { CompanyHistory } from "@/lib/domain/company";
import { makeComparisonHistory } from "../fixtures/comparison-fixtures";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  usePathname: () => "/companies/ACT",
  useSearchParams: () => new URLSearchParams(),
}));

function makeHistory(count: number): CompanyHistory {
  return {
    company: {
      id: "company-1",
      ticker: "ACT",
      name: "Acme Corp",
      sector: null,
      description: null,
      firstReportPeriodEnd: "2016-06-30",
      latestReportPeriodEnd: "2024-06-30",
      reportCount: count + 1,
      comparisonCount: count,
      latestComparisonId: `cmp-${count - 1}`,
      historicalPeakComparisonId: null,
      displayOrder: 0,
      hasCurrentData: true,
      latestReportSideQuality: "GOOD",
      latestReportSideQualityLabel: "Analysis ready",
      dataCoverageNote: "Coverage spans 2016–2024 across 9 reports and 8 comparisons.",
    },
    comparisons: makeComparisonHistory(count),
  };
}

let mockHistory: CompanyHistory | null = makeHistory(5);
let mockShouldThrow = false;

vi.mock("@/lib/repositories/postgres-company-repository", () => ({
  PostgresCompanyRepository: class {
    async getCompanyHistory() {
      if (mockShouldThrow) throw new Error("connection refused");
      return mockHistory;
    }
  },
}));

const { default: CompanyPage } = await import("@/app/companies/[ticker]/page");
const { default: CompanyPageError } = await import("@/app/companies/[ticker]/error");

describe("CompanyPage", () => {
  it("renders the company header, coverage note, full-history chart, and navigator", async () => {
    mockHistory = makeHistory(5);
    mockShouldThrow = false;
    const jsx = await CompanyPage({
      params: Promise.resolve({ ticker: "ACT" }),
      searchParams: Promise.resolve({}),
    });
    render(jsx);
    expect(screen.getByRole("heading", { name: "Acme Corp" })).toBeInTheDocument();
    expect(screen.getByText(/Coverage spans/)).toBeInTheDocument();
    expect(screen.getAllByRole("tab").length).toBeGreaterThan(0); // metric selector
    expect(screen.getByTestId("navigator-compact")).toBeInTheDocument();
  });

  it("selects and previews the latest comparison by default (no query param)", async () => {
    mockHistory = makeHistory(5);
    const jsx = await CompanyPage({ params: Promise.resolve({ ticker: "ACT" }), searchParams: Promise.resolve({}) });
    render(jsx);
    expect(screen.getByText("Selected comparison")).toBeInTheDocument();
    expect(screen.getByText("View full comparison →")).toHaveAttribute("href", "/comparisons/cmp-4");
  });

  it("falls back safely to the latest comparison for an invalid ?comparison= value, never crashes", async () => {
    mockHistory = makeHistory(5);
    const jsx = await CompanyPage({
      params: Promise.resolve({ ticker: "ACT" }),
      searchParams: Promise.resolve({ comparison: "not-a-real-id" }),
    });
    render(jsx);
    expect(screen.getByText("View full comparison →")).toHaveAttribute("href", "/comparisons/cmp-4");
  });

  it("selects the comparison named by a valid ?comparison= value", async () => {
    mockHistory = makeHistory(5);
    const jsx = await CompanyPage({
      params: Promise.resolve({ ticker: "ACT" }),
      searchParams: Promise.resolve({ comparison: "cmp-1" }),
    });
    render(jsx);
    expect(screen.getByText("View full comparison →")).toHaveAttribute("href", "/comparisons/cmp-1");
  });

  it("calls notFound() for an unknown ticker", async () => {
    mockHistory = null;
    await expect(
      CompanyPage({ params: Promise.resolve({ ticker: "ZZZ" }), searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it("throws instead of swallowing the error, so Next.js does not cache a failed render", async () => {
    mockShouldThrow = true;
    await expect(
      CompanyPage({ params: Promise.resolve({ ticker: "ACT" }), searchParams: Promise.resolve({}) }),
    ).rejects.toThrow("connection refused");
    mockShouldThrow = false;
  });

  it("renders a safe error state via the route error boundary", () => {
    render(<CompanyPageError error={new Error("connection refused")} reset={() => {}} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
