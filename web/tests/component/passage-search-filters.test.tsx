/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PassageSearchFilters } from "@/components/PassageSearchFilters";
import { parsePassageSearchParams } from "@/lib/services/passage-search-params";
import type { PassageFilterOptions } from "@/lib/domain/passage";

const FILTER_OPTIONS: PassageFilterOptions = {
  companies: [{ value: "ACT", label: "Acme Corp (ACT)" }],
  alignmentStatuses: [{ value: "NEW", label: "New" }],
  confidenceLevels: [{ value: "HIGH", label: "High confidence" }],
  passageTypes: [{ value: "LIST", label: "List" }],
  categories: [{ value: "risk", label: "Risk" }],
  subcategoriesByCategory: { risk: [{ value: "climate_environmental", label: "Climate environmental" }] },
  reportSideQualities: [{ value: "GOOD", label: "GOOD" }],
  alignmentChangeQualities: [{ value: "USABLE", label: "USABLE" }],
};

describe("PassageSearchFilters", () => {
  it("has an accessible search landmark and labeled query input", () => {
    render(<PassageSearchFilters params={parsePassageSearchParams({})} filterOptions={FILTER_OPTIONS} />);
    expect(screen.getByRole("search", { name: "Passage search" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search passage text")).toBeInTheDocument();
  });

  it("has a clear submit button and a reset link back to /passages", () => {
    render(<PassageSearchFilters params={parsePassageSearchParams({})} filterOptions={FILTER_OPTIONS} />);
    expect(screen.getByRole("button", { name: "Search" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Reset" })).toHaveAttribute("href", "/passages");
  });

  it("pre-fills fields from the current params", () => {
    render(<PassageSearchFilters params={parsePassageSearchParams({ q: "liquidity", company: "ACT" })} filterOptions={FILTER_OPTIONS} />);
    expect(screen.getByLabelText("Search passage text")).toHaveValue("liquidity");
    expect(screen.getByLabelText("Company")).toHaveValue("ACT");
  });

  it("only shows the subcategory field once a category is selected", () => {
    const { rerender } = render(<PassageSearchFilters params={parsePassageSearchParams({})} filterOptions={FILTER_OPTIONS} />);
    expect(screen.queryByLabelText("Subcategory")).not.toBeInTheDocument();
    rerender(<PassageSearchFilters params={parsePassageSearchParams({ category: "risk" })} filterOptions={FILTER_OPTIONS} />);
    expect(screen.getByLabelText("Subcategory")).toBeInTheDocument();
  });

  it("labels every filter control", () => {
    render(<PassageSearchFilters params={parsePassageSearchParams({})} filterOptions={FILTER_OPTIONS} />);
    expect(screen.getByLabelText("Company")).toBeInTheDocument();
    expect(screen.getByLabelText("Alignment status")).toBeInTheDocument();
    expect(screen.getByLabelText("Confidence")).toBeInTheDocument();
    expect(screen.getByLabelText("Passage type")).toBeInTheDocument();
    expect(screen.getByLabelText("Sort")).toBeInTheDocument();
  });
});
