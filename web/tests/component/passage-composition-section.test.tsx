/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PassageCompositionSection } from "@/components/PassageCompositionSection";
import type { PassageComposition } from "@/lib/domain/comparison";

function makeComposition(overrides: Partial<PassageComposition> = {}): PassageComposition {
  return {
    comparisonId: "cmp-1",
    totalCount: 10,
    buckets: [
      { status: "NEW", count: 3, share: 0.3 },
      { status: "REMOVED", count: 2, share: 0.2 },
      { status: "SUBSTANTIALLY_MODIFIED", count: 1, share: 0.1 },
      { status: "LIGHTLY_MODIFIED", count: 1, share: 0.1 },
      { status: "UNCHANGED", count: 2, share: 0.2 },
      { status: "AMBIGUOUS", count: 1, share: 0.1 },
    ],
    qualityNote: "Composition reflects passage-level alignment status.",
    ...overrides,
  };
}

describe("PassageCompositionSection", () => {
  it("renders a count card for every one of the six statuses, including UNCHANGED", () => {
    render(<PassageCompositionSection composition={makeComposition()} />);
    expect(screen.getByText("New")).toBeInTheDocument();
    expect(screen.getByText("Removed")).toBeInTheDocument();
    expect(screen.getByText("Substantially modified")).toBeInTheDocument();
    expect(screen.getByText("Lightly modified")).toBeInTheDocument();
    expect(screen.getByText("Unchanged")).toBeInTheDocument();
    expect(screen.getByText("Ambiguous")).toBeInTheDocument();
  });

  it("shows the total passage count and the quality note", () => {
    render(<PassageCompositionSection composition={makeComposition()} />);
    expect(screen.getByText("10 aligned passages total")).toBeInTheDocument();
    expect(screen.getByText("Composition reflects passage-level alignment status.")).toBeInTheDocument();
  });

  it("renders an accessible image summary with counts and shares (not just a color bar)", () => {
    render(<PassageCompositionSection composition={makeComposition()} />);
    const bar = screen.getByRole("img");
    expect(bar).toHaveAccessibleName(/New: 30\.0% \(3 passages\)/);
  });

  it("renders an empty state when there are zero aligned passages", () => {
    render(<PassageCompositionSection composition={makeComposition({ totalCount: 0, buckets: makeComposition().buckets.map((b) => ({ ...b, count: 0, share: 0 })) })} />);
    expect(screen.getByText(/No passage-composition data available/)).toBeInTheDocument();
  });
});
