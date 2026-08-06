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
const { default: CompaniesHomeError } = await import("@/app/(home)/error");

describe("Companies home page -- database unavailable", () => {
  it("throws instead of swallowing the error, so Next.js does not cache a failed render", async () => {
    // A page.tsx that catches and returns a 200 ErrorState would get that
    // failure baked into the ISR cache for the revalidate window. Letting
    // it throw means Next treats the request as failed and keeps serving
    // the last good cached page to other visitors.
    await expect(CompaniesHomePage()).rejects.toThrow("connection refused");
  });

  it("renders a clear service-unavailable state via the route error boundary", () => {
    render(<CompaniesHomeError error={new Error("connection refused")} reset={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Company data is temporarily unavailable");
    // Never render a fabricated "0 companies" summary alongside the error.
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
