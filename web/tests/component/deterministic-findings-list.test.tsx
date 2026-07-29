/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DeterministicFindingsList } from "@/components/DeterministicFindingsList";
import type { DeterministicFinding } from "@/lib/domain/comparison";

function makeFinding(overrides: Partial<DeterministicFinding> = {}): DeterministicFinding {
  return {
    key: "largest_risk_introduction",
    slot: "primary",
    headline: "Risk language introduced",
    description: "New risk-related language was introduced.",
    supportingValue: 2.1,
    supportingValueDisplay: "+2.10 / 1,000 words",
    supportingUnit: "rate_per_1000_words",
    ...overrides,
  };
}

describe("DeterministicFindingsList", () => {
  it("renders each finding's headline and description", () => {
    render(<DeterministicFindingsList findings={[makeFinding()]} />);
    expect(screen.getByText("Risk language introduced")).toBeInTheDocument();
    expect(screen.getByText("New risk-related language was introduced.")).toBeInTheDocument();
  });

  it("labels each slot distinctly (primary/secondary/tertiary)", () => {
    render(
      <DeterministicFindingsList
        findings={[
          makeFinding({ slot: "primary" }),
          makeFinding({ slot: "secondary", key: "largest_risk_removal", headline: "Risk language removed" }),
        ]}
      />,
    );
    expect(screen.getByText("Primary finding")).toBeInTheDocument();
    expect(screen.getByText("Secondary finding")).toBeInTheDocument();
  });

  it("renders a restrained empty state when there are no findings", () => {
    render(<DeterministicFindingsList findings={[]} />);
    expect(screen.getByText(/No deterministic findings/)).toBeInTheDocument();
  });

  it("renders fewer than three items without a placeholder for the missing slots", () => {
    render(<DeterministicFindingsList findings={[makeFinding()]} />);
    expect(screen.queryByText("Secondary finding")).not.toBeInTheDocument();
    expect(screen.queryByText("Tertiary finding")).not.toBeInTheDocument();
  });
});
