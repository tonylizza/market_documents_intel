/** @vitest-environment jsdom */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { METHODOLOGY_SECTIONS } from "@/lib/content/methodology-sections";

vi.mock("@/lib/repositories/postgres-methodology-repository", () => ({
  PostgresMethodologyRepository: class {
    async getMetricDefinitions() {
      return [
        {
          metricKey: "disclosure_change_score",
          displayName: "Overall disclosure change",
          shortDescription: "How much disclosures changed.",
          technicalDescription: "Composite score.",
          unit: "score_0_1",
          directionInterpretation: "Higher means more change.",
          methodologyAnchor: "Milestone 3",
        },
      ];
    }
    async getMethodologyContentData() {
      return {
        metrics: await this.getMetricDefinitions(),
        summary: {
          companyCount: 6,
          reportCount: 30,
          comparisonCount: 25,
          earliestPeriodEnd: "2016-06-30",
          latestPeriodEnd: "2025-12-31",
          publicationNote: "Data reflects the currently active publication.",
        },
      };
    }
  },
}));

const { default: MethodologyPage } = await import("@/app/methodology/page");

describe("Methodology page", () => {
  it("renders every required section", async () => {
    render(await MethodologyPage());
    for (const section of METHODOLOGY_SECTIONS) {
      expect(screen.getByRole("heading", { name: section.title })).toBeInTheDocument();
    }
  });

  it("renders the non-investment-advice statement", async () => {
    render(await MethodologyPage());
    expect(screen.getByText(/does not provide investment advice/)).toBeInTheDocument();
  });

  it("renders distinct quality vocabularies for all three dimensions", async () => {
    render(await MethodologyPage());
    expect(screen.getByText("Report-side quality")).toBeInTheDocument();
    expect(screen.getByText("Alignment-change quality")).toBeInTheDocument();
    expect(screen.getByText("Disclosure-change quality")).toBeInTheDocument();
    // Report-side and disclosure-change share "Review recommended" wording
    // (both appear -- once per legend); alignment-change's NEEDS_REVIEW
    // tier reads differently ("Attribution uncertain"), proving the
    // vocabularies are genuinely distinct, not one map reused three times.
    expect(screen.getAllByText("Review recommended").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Attribution uncertain")).toBeInTheDocument();
  });

  it("renders the metric catalog from metric_definitions", async () => {
    render(await MethodologyPage());
    expect(screen.getByText("Overall disclosure change")).toBeInTheDocument();
  });
});
