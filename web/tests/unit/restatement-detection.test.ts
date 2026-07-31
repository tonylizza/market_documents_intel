import { describe, expect, it } from "vitest";
import { isRestatementFlagged, hasExplanatoryLink, restatementChronologyIsClear, findSupersededPassageIds } from "@/lib/services/qa/restatement-detection";
import type { SelectedEvidence } from "@/lib/domain/qa-evidence";
import type { RetrievalContext } from "@/lib/domain/retrieval";

function context(overrides: Partial<RetrievalContext> = {}): RetrievalContext {
  return {
    contextId: "ctx-1",
    passageId: "passage-1",
    contextType: "COMPARISON_LINKED",
    passageComparisonId: "pc-1",
    reportComparisonId: "rc-1",
    reportId: "report-1",
    companyId: "company-1",
    companyTicker: "SBP",
    companyName: "Sabvest Capital Limited",
    reportSide: "EARLIER",
    alignmentStatus: "UNCHANGED",
    alignmentType: "ONE_TO_ONE",
    confidence: "HIGH",
    reportPeriodEnd: "2022-12-31",
    earlierPeriodEnd: "2022-12-31",
    laterPeriodEnd: "2023-12-31",
    heading: "6.2 Restatement",
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
    lastPageNumber: 10,
    wordCount: 40,
    text: "The subsidiaries were incorrectly consolidated in the prior period and have been restated.",
    categories: ["financial_condition"],
    riskSubcategories: [],
    ...overrides,
  };
}

function evidence(overrides: Partial<SelectedEvidence> = {}, contextOverrides: Partial<RetrievalContext> = {}): SelectedEvidence {
  const ctx = context(contextOverrides);
  return {
    candidateId: ctx.contextId,
    passageId: ctx.passageId,
    retrievalContextId: ctx.contextId,
    context: ctx,
    citation: {
      publicationId: "pub-1",
      retrievalContextId: ctx.contextId,
      passageId: ctx.passageId,
      passageComparisonId: ctx.passageComparisonId,
      reportComparisonId: ctx.reportComparisonId,
      reportSide: ctx.reportSide,
      reportId: ctx.reportId,
      firstPageNumber: ctx.firstPageNumber,
      lastPageNumber: ctx.lastPageNumber,
      label: "SBP, p. 10",
    },
    sources: ["keyword"],
    lexicalRankPosition: 1,
    semanticRawRank: null,
    semanticAdjustedRank: null,
    semanticRawSimilarity: null,
    semanticAdjustedScore: null,
    qualityFactor: null,
    qualityExplanationCode: null,
    rrfRank: 1,
    relevanceScore: 0.8,
    relevanceRank: 1,
    rerankerMethod: "baseline",
    numericFragmentSeverity: null,
    conceptCoverageScore: 1,
    directResponsivenessScore: 1,
    directResponsivenessRank: 1,
    evidenceEligible: true,
    ineligibilityReasons: [],
    selectionOrder: 1,
    newFacetsCovered: [],
    ...overrides,
  };
}

describe("isRestatementFlagged", () => {
  it("flags a passage using restatement vocabulary", () => {
    expect(isRestatementFlagged(evidence())).toBe(true);
  });

  it("flags a passage whose alignment status is AMBIGUOUS even without restatement wording", () => {
    const item = evidence({}, { alignmentStatus: "AMBIGUOUS", text: "Ordinary prose about board composition." });
    expect(isRestatementFlagged(item)).toBe(true);
  });

  it("does not flag ordinary, unambiguous prose", () => {
    const item = evidence({}, { alignmentStatus: "UNCHANGED", heading: "Board composition", text: "The board comprises five non-executive directors." });
    expect(isRestatementFlagged(item)).toBe(false);
  });
});

describe("hasExplanatoryLink", () => {
  it("detects the explanatory-link vocabulary", () => {
    expect(hasExplanatoryLink(evidence({}, { text: "This disclosure was reclassified and superseded by the current-year note." }))).toBe(true);
  });

  it("does not detect a link in unrelated text", () => {
    expect(hasExplanatoryLink(evidence({}, { text: "The board comprises five non-executive directors." }))).toBe(false);
  });
});

describe("restatementChronologyIsClear", () => {
  it("is clear for two flagged items with distinct EARLIER/LATER sides", () => {
    const earlier = evidence({ candidateId: "e" }, { contextId: "e", passageId: "p-e", reportSide: "EARLIER" });
    const later = evidence({ candidateId: "l" }, { contextId: "l", passageId: "p-l", reportSide: "LATER" });
    expect(restatementChronologyIsClear([earlier, later])).toBe(true);
  });

  it("is ambiguous when both flagged items share the same report side", () => {
    const a = evidence({ candidateId: "a" }, { contextId: "a", passageId: "p-a", reportSide: "EARLIER" });
    const b = evidence({ candidateId: "b" }, { contextId: "b", passageId: "p-b", reportSide: "EARLIER" });
    expect(restatementChronologyIsClear([a, b])).toBe(false);
  });

  it("is ambiguous for a single item with no report side", () => {
    const single = evidence({}, { reportSide: null });
    expect(restatementChronologyIsClear([single])).toBe(false);
  });
});

describe("findSupersededPassageIds", () => {
  it("marks the EARLIER passage superseded when a LATER passage explicitly links back to it", () => {
    const earlier = evidence({ candidateId: "e" }, { contextId: "e", passageId: "p-e", reportSide: "EARLIER" });
    const later = evidence(
      { candidateId: "l" },
      { contextId: "l", passageId: "p-l", reportSide: "LATER", text: "This figure supersedes the previously reported, restated amount." },
    );
    expect(findSupersededPassageIds([earlier, later])).toEqual(["p-e"]);
  });

  it("returns nothing when there is no later explanatory link", () => {
    const earlier = evidence({ candidateId: "e" }, { contextId: "e", passageId: "p-e", reportSide: "EARLIER" });
    const later = evidence({ candidateId: "l" }, { contextId: "l", passageId: "p-l", reportSide: "LATER", text: "Ordinary unrelated prose." });
    expect(findSupersededPassageIds([earlier, later])).toEqual([]);
  });

  it("returns nothing when fewer than two items are restatement-flagged", () => {
    const single = evidence();
    expect(findSupersededPassageIds([single])).toEqual([]);
  });
});
