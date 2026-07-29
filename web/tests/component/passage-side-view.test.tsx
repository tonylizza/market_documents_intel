/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PassageSideView } from "@/components/PassageSideView";
import type { PassageSideDetail } from "@/lib/domain/passage";

describe("PassageSideView", () => {
  it("shows the full, uncapped passage text", () => {
    const longText = "word ".repeat(2000).trim();
    const side: PassageSideDetail = {
      passageId: "p1",
      heading: "Long passage",
      text: longText,
      wordCount: 2000,
      firstPageNumber: 1,
      lastPageNumber: 3,
      passageType: "MULTI_PARAGRAPH",
      structuredContentCategory: null,
      primaryNarrativeEligible: true,
      featureEligible: false,
    };
    render(<PassageSideView label="Later disclosure" side={side} />);
    expect(screen.getByText(longText)).toBeInTheDocument();
  });

  it("shows page range, word count, and eligibility badges", () => {
    const side: PassageSideDetail = {
      passageId: "p1",
      heading: "Impairment",
      text: "text",
      wordCount: 42,
      firstPageNumber: 5,
      lastPageNumber: 6,
      passageType: "PARAGRAPH",
      structuredContentCategory: "list_content",
      primaryNarrativeEligible: true,
      featureEligible: true,
    };
    render(<PassageSideView label="Earlier disclosure" side={side} />);
    expect(screen.getByText("Pages 5–6")).toBeInTheDocument();
    expect(screen.getByText("42 words")).toBeInTheDocument();
    expect(screen.getByText("Primary narrative eligible")).toBeInTheDocument();
    expect(screen.getByText("Feature eligible")).toBeInTheDocument();
    expect(screen.getByText("List content")).toBeInTheDocument();
  });

  it("renders a placeholder for a null heading", () => {
    const side: PassageSideDetail = {
      passageId: "p1",
      heading: null,
      text: "text",
      wordCount: 1,
      firstPageNumber: 1,
      lastPageNumber: 1,
      passageType: "PARAGRAPH",
      structuredContentCategory: null,
      primaryNarrativeEligible: false,
      featureEligible: false,
    };
    render(<PassageSideView label="Earlier disclosure" side={side} />);
    expect(screen.getByText("(No heading)")).toBeInTheDocument();
  });
});
