import { describe, expect, it } from "vitest";
import { IdentitySemanticReranker, QualityAdjustedSemanticReranker } from "@/lib/services/semantic-reranker";
import type { SemanticCandidate } from "@/lib/domain/retrieval";

function candidate(overrides: Partial<SemanticCandidate> = {}): SemanticCandidate {
  return {
    passageId: "p1",
    similarity: 0.8,
    heading: null,
    text: "The board reviews risk management effectiveness annually across the group.",
    wordCount: 11,
    hasLanguageSignal: false,
    headingFrequency: 0,
    ...overrides,
  };
}

describe("IdentitySemanticReranker (no-remediation baseline)", () => {
  it("preserves rank and similarity unchanged", () => {
    const candidates = [candidate({ passageId: "a", similarity: 0.9 }), candidate({ passageId: "b", similarity: 0.7 })];
    const reranked = new IdentitySemanticReranker().rerank("query", candidates);
    expect(reranked.map((r) => r.passageId)).toEqual(["a", "b"]);
    expect(reranked[0].adjustedScore).toBe(0.9);
    expect(reranked[0].rawSimilarity).toBe(0.9);
    expect(reranked[0].qualityFactor).toBe(1);
  });
});

describe("QualityAdjustedSemanticReranker", () => {
  it("demotes a generic short heading-only fragment below a substantive lower-similarity passage", () => {
    const fragment = candidate({
      passageId: "fragment",
      similarity: 0.85,
      heading: "Operations (continued)",
      text: "Operations (continued)",
      wordCount: 2,
    });
    const substantive = candidate({
      passageId: "substantive",
      similarity: 0.78,
      heading: "Liquidity risk",
      text: "The group maintains adequate liquidity headroom and there is no material uncertainty regarding going concern.",
      wordCount: 17,
    });
    const reranked = new QualityAdjustedSemanticReranker().rerank("query", [fragment, substantive]);
    expect(reranked[0].passageId).toBe("substantive");
    expect(reranked.find((r) => r.passageId === "fragment")?.explanationCode).toBe("HEADING_ONLY_FRAGMENT");
  });

  it("retains a useful short substantive passage with a real language signal", () => {
    const shortFinancial = candidate({
      passageId: "short-financial",
      similarity: 0.75,
      heading: "Going concern",
      text: "Going concern",
      wordCount: 2,
      hasLanguageSignal: true,
    });
    const reranked = new QualityAdjustedSemanticReranker().rerank("query", [shortFinancial]);
    expect(reranked[0].qualityFactor).toBe(1);
    expect(reranked[0].adjustedScore).toBe(0.75);
    expect(reranked[0].explanationCode).toBe("RETAINED_SHORT_FINANCIAL_SENTENCE");
  });

  it("leaves a long substantive passage unaffected", () => {
    const long = candidate({ passageId: "long", similarity: 0.6, wordCount: 120 });
    const reranked = new QualityAdjustedSemanticReranker().rerank("query", [long]);
    expect(reranked[0].adjustedScore).toBe(0.6);
    expect(reranked[0].explanationCode).toBe("NO_QUALITY_ADJUSTMENT");
  });

  it("is deterministic across repeated calls with identical input", () => {
    const candidates = [candidate({ passageId: "a" }), candidate({ passageId: "b", heading: "BACK", text: "BACK", wordCount: 1, headingFrequency: 80 })];
    const first = new QualityAdjustedSemanticReranker().rerank("q", candidates);
    const second = new QualityAdjustedSemanticReranker().rerank("q", candidates);
    expect(first).toEqual(second);
  });

  it("breaks ties deterministically by original rank, then passage id", () => {
    const a = candidate({ passageId: "z", similarity: 0.5, wordCount: 100 });
    const b = candidate({ passageId: "a", similarity: 0.5, wordCount: 100 });
    const reranked = new QualityAdjustedSemanticReranker().rerank("q", [a, b]);
    // Both have identical adjusted scores (no adjustment applied); "z" was
    // first in the input (better original rank), so it wins the tie.
    expect(reranked.map((r) => r.passageId)).toEqual(["z", "a"]);
  });

  it("always preserves raw similarity separately from the adjusted score", () => {
    const fragment = candidate({ heading: "USD", text: "USD", wordCount: 1, headingFrequency: 429, similarity: 0.82 });
    const [result] = new QualityAdjustedSemanticReranker().rerank("q", [fragment]);
    expect(result.rawSimilarity).toBe(0.82);
    expect(result.adjustedScore).not.toBe(result.rawSimilarity);
    expect(result.adjustedScore).toBeLessThan(result.rawSimilarity);
  });

  it("never produces an adjustment factor of exactly 0 (bounded, never deleted)", () => {
    const fragment = candidate({ heading: "USD", text: "USD", wordCount: 1, headingFrequency: 429 });
    const [result] = new QualityAdjustedSemanticReranker().rerank("q", [fragment]);
    expect(result.qualityFactor).toBeGreaterThan(0);
  });

  it("assigns explanation codes to every candidate", () => {
    const candidates = [candidate({ passageId: "a" }), candidate({ passageId: "b", heading: "BACK", text: "BACK", wordCount: 1, headingFrequency: 80 })];
    const reranked = new QualityAdjustedSemanticReranker().rerank("q", candidates);
    for (const r of reranked) {
      expect(r.explanationCode).toBeTruthy();
    }
  });

  it("preserves the full candidate count (never truncates)", () => {
    const candidates = Array.from({ length: 25 }, (_, i) => candidate({ passageId: `p${i}`, similarity: Math.random() }));
    const reranked = new QualityAdjustedSemanticReranker().rerank("q", candidates);
    expect(reranked).toHaveLength(25);
  });

  it("accepts a custom quality-adjustment config", () => {
    const fragment = candidate({ heading: "USD", text: "USD", wordCount: 1, headingFrequency: 429, similarity: 0.9 });
    const strict = new QualityAdjustedSemanticReranker({
      headingOnlyFragmentFactor: 0.1,
      genericHeadingFactor: 0.1,
      lowSubstantiveFactor: 0.1,
    }).rerank("q", [fragment]);
    const lenient = new QualityAdjustedSemanticReranker({
      headingOnlyFragmentFactor: 0.95,
      genericHeadingFactor: 0.95,
      lowSubstantiveFactor: 0.95,
    }).rerank("q", [fragment]);
    expect(strict[0].adjustedScore).toBeLessThan(lenient[0].adjustedScore);
  });
});
