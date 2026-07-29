/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QualityBadge } from "@/components/QualityBadge";

describe("QualityBadge", () => {
  it("renders the accessible name combining dimension and label", () => {
    render(<QualityBadge dimension="report-side" quality="NEEDS_REVIEW" label="Review recommended" />);
    expect(screen.getByRole("status", { name: "Report-side quality: Review recommended" })).toBeInTheDocument();
  });

  it("uses a distinct accessible name for the same raw tier on a different dimension", () => {
    render(<QualityBadge dimension="alignment-change" quality="NEEDS_REVIEW" label="Attribution uncertain" />);
    expect(screen.getByRole("status", { name: "Alignment-change quality: Attribution uncertain" })).toBeInTheDocument();
  });

  it("falls back to the dimension vocabulary when label is missing", () => {
    render(<QualityBadge dimension="disclosure-change" quality="NEEDS_REVIEW" label={null} />);
    expect(screen.getByText("Review recommended")).toBeInTheDocument();
  });

  it("never fabricates text for a null quality/label pair", () => {
    render(<QualityBadge dimension="report-side" quality={null} label={null} />);
    expect(screen.getByText("Not available")).toBeInTheDocument();
  });

  it("compact mode omits the visible dimension prefix but keeps it in the accessible name", () => {
    render(<QualityBadge dimension="report-side" quality="GOOD" label="Analysis ready" compact />);
    expect(screen.queryByText("Report-side quality")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Report-side quality: Analysis ready" })).toBeInTheDocument();
  });
});
