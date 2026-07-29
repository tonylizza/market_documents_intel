/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PassageLanguageSignalsSection } from "@/components/PassageLanguageSignalsSection";
import type { PassageLanguageSignal } from "@/lib/domain/passage";

describe("PassageLanguageSignalsSection", () => {
  it("shows an empty state when every signal has a zero raw count", () => {
    const signals: PassageLanguageSignal[] = [
      { reportSide: "EARLIER", category: "positive", subcategory: null, rawCount: 0, negatedCount: 0, adjustedCount: 0, ratePer1000: 0, isIntroduced: false, isRemoved: false, isRetained: false },
    ];
    render(<PassageLanguageSignalsSection signals={signals} />);
    expect(screen.getByText("No language signals present")).toBeInTheDocument();
  });

  it("groups nonzero signals by report side", () => {
    const signals: PassageLanguageSignal[] = [
      { reportSide: "EARLIER", category: "risk", subcategory: "liquidity", rawCount: 2, negatedCount: 0, adjustedCount: 2, ratePer1000: 8, isIntroduced: false, isRemoved: false, isRetained: true },
      { reportSide: "LATER", category: "governance", subcategory: "remuneration", rawCount: 1, negatedCount: 0, adjustedCount: 1, ratePer1000: 4, isIntroduced: true, isRemoved: false, isRetained: false },
    ];
    render(<PassageLanguageSignalsSection signals={signals} />);
    expect(screen.getByText("Earlier report")).toBeInTheDocument();
    expect(screen.getByText("Later report")).toBeInTheDocument();
    expect(screen.getByText("Retained")).toBeInTheDocument();
    expect(screen.getByText("Introduced")).toBeInTheDocument();
  });

  it("renders a core category (no subcategory) without a dangling separator", () => {
    const signals: PassageLanguageSignal[] = [
      { reportSide: "EARLIER", category: "uncertainty", subcategory: null, rawCount: 1, negatedCount: 0, adjustedCount: 1, ratePer1000: 4, isIntroduced: null, isRemoved: null, isRetained: null },
    ];
    render(<PassageLanguageSignalsSection signals={signals} />);
    expect(screen.getByText("Uncertainty")).toBeInTheDocument();
  });

  it("tolerates null adjusted/negated/rate fields", () => {
    const signals: PassageLanguageSignal[] = [
      { reportSide: "EARLIER", category: "risk", subcategory: "debt", rawCount: 1, negatedCount: null, adjustedCount: null, ratePer1000: null, isIntroduced: null, isRemoved: null, isRetained: null },
    ];
    render(<PassageLanguageSignalsSection signals={signals} />);
    expect(screen.getAllByText("Not available").length).toBeGreaterThan(0);
  });
});
