/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/repositories/postgres-company-repository", () => ({
  PostgresCompanyRepository: class {
    async listCompanies() {
      throw new Error("connection refused");
    }
    async getCompanyCardSummaries() {
      throw new Error("connection refused");
    }
    async getLatestComparisonSummaries() {
      throw new Error("connection refused");
    }
    async getApplicationDataSummary() {
      throw new Error("connection refused");
    }
  },
  LANGUAGE_DISCOVERY_TYPES: [],
}));

const { default: CompaniesHomePage } = await import("@/app/(home)/page");

describe("Companies home page -- database unavailable", () => {
  it("renders a clear service-unavailable state instead of misleading zeroes", async () => {
    render(await CompaniesHomePage());
    expect(screen.getByRole("alert")).toHaveTextContent("Company data is temporarily unavailable");
    // Never render a fabricated "0 companies" summary alongside the error.
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
