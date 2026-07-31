/** @vitest-environment jsdom */
import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { RetrievalResultCard } from "@/components/RetrievalResultCard";
import type { GroupedRetrievalResult, RetrievalContext } from "@/lib/domain/retrieval";

function makeContext(overrides: Partial<RetrievalContext> = {}): RetrievalContext {
  return {
    contextId: "ctx-1",
    passageId: "passage-1",
    contextType: "COMPARISON_LINKED",
    passageComparisonId: "pc-1",
    reportComparisonId: "rc-1",
    reportId: "report-1",
    companyId: "company-1",
    companyTicker: "KP2",
    companyName: "Kappa Two",
    reportSide: "LATER",
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    reportPeriodEnd: "2024-06-30",
    earlierPeriodEnd: "2023-06-30",
    laterPeriodEnd: "2024-06-30",
    heading: "Liquidity risk",
    passageType: "PARAGRAPH",
    structuredContentCategory: null,
    primaryNarrativeEligible: true,
    featureEligible: true,
    reportSideQuality: "GOOD",
    alignmentChangeQuality: "GOOD",
    collisionFlag: false,
    splitMergeFlag: false,
    irregularGapFlag: false,
    firstPageNumber: 10,
    lastPageNumber: 11,
    wordCount: 50,
    text: "The group maintains adequate liquidity headroom.",
    categories: [],
    riskSubcategories: [],
    ...overrides,
  };
}

function makeResult(overrides: Partial<GroupedRetrievalResult> = {}): GroupedRetrievalResult {
  const context = makeContext();
  return {
    context,
    additionalContexts: [],
    excerpt: [{ text: "The group maintains adequate ", matched: false }, { text: "liquidity", matched: true }, { text: " headroom.", matched: false }],
    headingHighlight: null,
    citation: {
      publicationId: "pub-1",
      retrievalContextId: context.contextId,
      passageId: context.passageId,
      passageComparisonId: context.passageComparisonId,
      reportComparisonId: context.reportComparisonId,
      reportSide: context.reportSide,
      reportId: context.reportId,
      firstPageNumber: context.firstPageNumber,
      lastPageNumber: context.lastPageNumber,
      label: "KP2, 2023->2024 comparison, later report, pp. 10-11",
    },
    diagnostics: {
      mode: "semantic",
      vectorSearchMode: "hnsw",
      semanticSimilarity: 0.72,
      qualityFactor: 1,
      adjustedSemanticScore: 0.72,
      qualityExplanationCode: "NO_QUALITY_ADJUSTMENT",
      semanticRawRank: 1,
      semanticAdjustedRank: 1,
      lexicalRankPosition: null,
      fusedScore: null,
      model: "BAAI/bge-small-en-v1.5",
      modelRevision: "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
      strength: "strong",
    },
    evidenceUrl: `/passages/${context.passageComparisonId}`,
    passageDetailUrl: `/passages/${context.passageComparisonId}`,
    finalRank: 1,
    hasAdditionalContexts: false,
    ...overrides,
  };
}

describe("RetrievalResultCard", () => {
  it("shows company, period/side, and page range", () => {
    render(<RetrievalResultCard result={makeResult()} />);
    expect(screen.getByText(/Kappa Two \(KP2\)/)).toBeInTheDocument();
    expect(screen.getByText(/Pages 10–11/)).toBeInTheDocument();
  });

  it("shows a weak-match badge only when diagnostics.strength is weak", () => {
    const { rerender } = render(<RetrievalResultCard result={makeResult()} />);
    expect(screen.queryByText("Weak match")).not.toBeInTheDocument();

    rerender(
      <RetrievalResultCard
        result={makeResult({ diagnostics: { ...makeResult().diagnostics, strength: "weak" } })}
      />,
    );
    expect(screen.getByText("Weak match")).toBeInTheDocument();
  });

  it("never renders raw vector data", () => {
    render(<RetrievalResultCard result={makeResult()} />);
    expect(document.body.textContent).not.toMatch(/\[-?\d\.\d+,\s*-?\d\.\d+/);
  });

  it("shows semantic similarity only inside the collapsed technical-details panel", () => {
    render(<RetrievalResultCard result={makeResult()} />);
    const details = screen.getByText("Technical details").closest("details");
    expect(details).not.toBeNull();
    expect(details?.textContent).toContain("0.720");
  });

  it("distinguishes raw similarity from an adjusted score when a quality adjustment was applied", () => {
    render(
      <RetrievalResultCard
        result={makeResult({
          diagnostics: {
            ...makeResult().diagnostics,
            semanticSimilarity: 0.82,
            qualityFactor: 0.5,
            adjustedSemanticScore: 0.41,
            qualityExplanationCode: "HEADING_ONLY_FRAGMENT",
            semanticRawRank: 1,
            semanticAdjustedRank: 4,
          },
        })}
      />,
    );
    const details = screen.getByText("Technical details").closest("details");
    expect(details?.textContent).toContain("0.820"); // raw
    expect(details?.textContent).toContain("0.410"); // adjusted
    expect(details?.textContent).not.toContain("HEADING_ONLY_FRAGMENT");
    expect(details?.textContent).toMatch(/heading with no body text/i);
  });

  it("never shows raw explanation codes in the UI, only plain-language notes", () => {
    render(
      <RetrievalResultCard
        result={makeResult({
          diagnostics: {
            ...makeResult().diagnostics,
            qualityFactor: 0.6,
            adjustedSemanticScore: 0.5,
            qualityExplanationCode: "SHORT_GENERIC_HEADING_PENALTY",
          },
        })}
      />,
    );
    expect(document.body.textContent).not.toContain("SHORT_GENERIC_HEADING_PENALTY");
  });

  it("omits the adjusted-score row when no adjustment was applied", () => {
    render(<RetrievalResultCard result={makeResult()} />);
    const details = screen.getByText("Technical details").closest("details");
    expect(details?.textContent).not.toContain("Adjusted semantic score");
  });

  it("renders a grouped-context expander when additional contexts exist, and expands them on click", () => {
    const additional = makeContext({ contextId: "ctx-2", reportSide: "EARLIER", earlierPeriodEnd: "2022-06-30", laterPeriodEnd: "2023-06-30" });
    render(<RetrievalResultCard result={makeResult({ additionalContexts: [additional], hasAdditionalContexts: true })} />);

    const button = screen.getByRole("button", { name: /Also appears in 1 other comparison/ });
    expect(button).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("does not render a grouped-context expander when there is only one context", () => {
    render(<RetrievalResultCard result={makeResult()} />);
    expect(screen.queryByText(/Also appears in/)).not.toBeInTheDocument();
  });

  it("shows the citation label and an evidence link", () => {
    render(<RetrievalResultCard result={makeResult()} />);
    expect(screen.getByText("KP2, 2023->2024 comparison, later report, pp. 10-11")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view evidence/i })).toHaveAttribute("href", "/passages/pc-1");
  });

  it("highlights matched excerpt terms", () => {
    render(<RetrievalResultCard result={makeResult()} />);
    expect(document.querySelectorAll("mark").length).toBeGreaterThanOrEqual(1);
  });
});
