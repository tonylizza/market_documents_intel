/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DiscoveryFilters } from "@/components/DiscoveryFilters";
import type { DiscoveryFilterOptions, DiscoveryFilterState } from "@/lib/domain/discovery";

const FILTERS: DiscoveryFilterState = {
  type: "largest_risk_introduction",
  scope: "corpus",
  company: null,
  minQuality: null,
  periodStart: null,
  periodEnd: null,
};

const FILTER_OPTIONS: DiscoveryFilterOptions = {
  companies: [{ ticker: "ACT", name: "Acme Corp" }],
  earliestPeriodEnd: "2016-06-30",
  latestPeriodEnd: "2024-06-30",
};

describe("DiscoveryFilters", () => {
  it("renders only the currently available types as ranking options", () => {
    render(
      <DiscoveryFilters
        availableTypes={["largest_risk_introduction", "largest_risk_removal"]}
        filters={FILTERS}
        filterOptions={FILTER_OPTIONS}
      />,
    );
    const select = screen.getByLabelText("Ranking") as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((o) => o.value);
    expect(optionValues).toEqual(["largest_risk_introduction", "largest_risk_removal"]);
  });

  it("builds the minimum-quality select from the selected type's own quality dimension vocabulary", () => {
    render(<DiscoveryFilters availableTypes={["largest_risk_introduction"]} filters={FILTERS} filterOptions={FILTER_OPTIONS} />);
    // largest_risk_introduction is gated on alignment-change quality --
    // its vocabulary ("Strong attribution"), never report-side wording
    // ("Analysis ready").
    expect(screen.getByRole("option", { name: "Strong attribution" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Analysis ready" })).not.toBeInTheDocument();
  });

  it("lists all companies from filterOptions plus an 'All companies' option", () => {
    render(<DiscoveryFilters availableTypes={["largest_risk_introduction"]} filters={FILTERS} filterOptions={FILTER_OPTIONS} />);
    expect(screen.getByRole("option", { name: "All companies" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Acme Corp (ACT)" })).toBeInTheDocument();
  });

  it("renders as a real GET form (works without JavaScript)", () => {
    render(<DiscoveryFilters availableTypes={["largest_risk_introduction"]} filters={FILTERS} filterOptions={FILTER_OPTIONS} />);
    const form = screen.getByRole("form", { name: "Discovery filters" });
    expect(form).toHaveAttribute("method", "get");
    expect(form).toHaveAttribute("action", "/discover");
  });

  it("all filter controls are keyboard-labeled (associated label for every input)", () => {
    render(<DiscoveryFilters availableTypes={["largest_risk_introduction"]} filters={FILTERS} filterOptions={FILTER_OPTIONS} />);
    expect(screen.getByLabelText("Ranking")).toBeInTheDocument();
    expect(screen.getByLabelText("Scope")).toBeInTheDocument();
    expect(screen.getByLabelText("Company")).toBeInTheDocument();
    expect(screen.getByLabelText("From")).toBeInTheDocument();
    expect(screen.getByLabelText("To")).toBeInTheDocument();
  });
});
