/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PassageDiffView } from "@/components/PassageDiffView";
import { buildTextDiff } from "@/lib/services/passage-diff";
import type { PassageSideDetail } from "@/lib/domain/passage";

function makeSide(overrides: Partial<PassageSideDetail> = {}): PassageSideDetail {
  return {
    passageId: "p1",
    heading: "Liquidity",
    text: "The group maintains adequate liquidity.",
    wordCount: 6,
    firstPageNumber: 1,
    lastPageNumber: 1,
    passageType: "HEADING_WITH_BODY",
    structuredContentCategory: null,
    primaryNarrativeEligible: true,
    featureEligible: true,
    ...overrides,
  };
}

describe("PassageDiffView", () => {
  it("shows both earlier and later disclosure headings", () => {
    const earlier = makeSide({ text: "the group maintains liquidity" });
    const later = makeSide({ text: "the group maintains adequate liquidity" });
    render(<PassageDiffView earlier={earlier} later={later} diff={buildTextDiff(earlier.text, later.text)} />);
    expect(screen.getByText("Earlier disclosure")).toBeInTheDocument();
    expect(screen.getByText("Later disclosure")).toBeInTheDocument();
  });

  it("highlights an inserted word on the later side", () => {
    const earlier = makeSide({ text: "the group maintains liquidity" });
    const later = makeSide({ text: "the group maintains adequate liquidity" });
    render(<PassageDiffView earlier={earlier} later={later} diff={buildTextDiff(earlier.text, later.text)} />);
    expect(screen.getByText(/adequate/)).toBeInTheDocument();
  });

  it("toggles to the original, unhighlighted text and back", async () => {
    const user = userEvent.setup();
    const earlier = makeSide({ text: "the group maintains liquidity" });
    const later = makeSide({ text: "the group maintains adequate liquidity" });
    render(<PassageDiffView earlier={earlier} later={later} diff={buildTextDiff(earlier.text, later.text)} />);

    const toggle = screen.getByRole("button", { name: "Show original text" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle);
    expect(screen.getByRole("button", { name: "Show highlighted differences" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(later.text)).toBeInTheDocument();
  });

  it("explains that highlighting is presentation-only, not the alignment algorithm", () => {
    const earlier = makeSide();
    const later = makeSide();
    render(<PassageDiffView earlier={earlier} later={later} diff={buildTextDiff(earlier.text, later.text)} />);
    expect(screen.getByText(/visual reading aid/i)).toBeInTheDocument();
  });

  it("shows a fallback note and the plain original text when diffed is false", () => {
    const earlier = makeSide({ text: "a".repeat(30000) });
    const later = makeSide({ text: "b" });
    const diff = buildTextDiff(earlier.text, later.text);
    render(<PassageDiffView earlier={earlier} later={later} diff={diff} />);
    expect(screen.getByText(/too long for highlighted differencing/i)).toBeInTheDocument();
  });
});
