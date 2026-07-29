/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { HighlightedText } from "@/components/HighlightedText";

describe("HighlightedText", () => {
  it("renders a matched span as a <mark> element", () => {
    render(<HighlightedText spans={[{ text: "liquidity", matched: true }]} />);
    const mark = screen.getByText("liquidity");
    expect(mark.tagName).toBe("MARK");
  });

  it("renders an unmatched span as plain text, not a <mark>", () => {
    render(<HighlightedText spans={[{ text: "ordinary text", matched: false }]} />);
    const node = screen.getByText("ordinary text");
    expect(node.tagName).not.toBe("MARK");
  });

  it("renders HTML-like text content as inert text, never parsed as markup", () => {
    render(<HighlightedText spans={[{ text: "<script>alert(1)</script>", matched: false }]} />);
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).not.toBeInTheDocument();
  });

  it("renders multiple spans in order", () => {
    const { container } = render(
      <HighlightedText
        spans={[
          { text: "The ", matched: false },
          { text: "liquidity", matched: true },
          { text: " position is strong.", matched: false },
        ]}
      />,
    );
    expect(container.textContent).toBe("The liquidity position is strong.");
  });
});
