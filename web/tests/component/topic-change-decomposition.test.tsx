/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TopicChangeDecomposition } from "@/components/TopicChangeDecomposition";
import type { TopicCategoryChange, TopicChangeDetail, TopicEvidencePassage } from "@/lib/domain/comparison";

function category(overrides: Partial<TopicCategoryChange> = {}): TopicCategoryChange {
  return {
    hitsEarlier: 100,
    hitsLater: 100,
    countChangePer1000: 0,
    densityChange: 0.05,
    topicChange: 0,
    supportingHits: 0,
    opposingHits: 0,
    changeConsistencyRatio: 0,
    largestPassageShare: 0.1,
    ...overrides,
  };
}

const DETAIL: TopicChangeDetail = {
  wordsEarlier: 50000,
  wordsLater: 53000,
  positiveRateChange: -2.4,
  negativeRateChange: 0.3,
  categories: {
    financial_condition: category({
      hitsEarlier: 71,
      hitsLater: 55,
      countChangePer1000: -0.9016,
      densityChange: -1.1027,
      topicChange: -0.9016,
      supportingHits: 24,
      opposingHits: 8,
      changeConsistencyRatio: -0.5,
      largestPassageShare: 0.156,
    }),
    governance: category(),
    uncertainty: category({ topicChange: 0.5, countChangePer1000: 1.1, densityChange: 0.5, hitsLater: 120 }),
  },
};

const EVIDENCE: TopicEvidencePassage[] = [
  {
    category: "financial_condition",
    reportSide: "LATER",
    passageComparisonId: "pc-1",
    hits: 7,
    heading: "Liquidity",
    excerpt: "Cash and debt facilities...",
    firstPageNumber: 12,
    alignmentStatus: "NEW",
    confidence: "LOW",
    alignmentCaveat: "Possibly moved or restructured: alignment confidence is weak, so similar text may appear elsewhere in the other report.",
  },
];

describe("TopicChangeDecomposition", () => {
  it("renders the decomposition with hits, legs, diagnostics and threshold status", () => {
    render(<TopicChangeDecomposition comparisonId="cmp-1" topicChange={DETAIL} netToneChange={-2.7} evidence={EVIDENCE} />);
    expect(screen.getByText(/Financial-condition language change: -0.90 \/ 1,000 words/)).toBeInTheDocument();
    expect(screen.getByText("71 → 55")).toBeInTheDocument();
    expect(screen.getByText(/24 hits with, 8 hits against/)).toBeInTheDocument();
    expect(screen.getAllByText(/Clears the Discover threshold/).length).toBe(1);
    expect(screen.getAllByText(/Below the Discover threshold/).length).toBe(2);
    expect(screen.getByText(/not financial health, financial performance, or financial risk/)).toBeInTheDocument();
  });

  it("labels weakly aligned evidence as possibly moved and never implies sentiment for net tone", () => {
    render(<TopicChangeDecomposition comparisonId="cmp-1" topicChange={DETAIL} netToneChange={-2.7} evidence={EVIDENCE} />);
    expect(screen.getByText(/^Possibly moved or restructured/)).toBeInTheDocument();
    expect(screen.getByText("Driven mainly by fewer positive words.")).toBeInTheDocument();
    expect(screen.getByText(/not management sentiment, outlook, or performance/)).toBeInTheDocument();
    expect(screen.getByText(/Clears the Discover net tone decline threshold/)).toBeInTheDocument();
  });

  it("renders an explicit empty state when no topic detail was published", () => {
    render(<TopicChangeDecomposition comparisonId="cmp-1" topicChange={null} netToneChange={null} evidence={[]} />);
    expect(screen.getByText(/No topic-change detail available/)).toBeInTheDocument();
  });
});
