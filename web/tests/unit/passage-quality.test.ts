import { describe, expect, it } from "vitest";
import {
  computeNumericFragmentSeverity,
  computePassageQualityFeatures,
  computeQualityAdjustment,
  DEFAULT_QUALITY_ADJUSTMENT_CONFIG,
  REPEATED_HEADING_FREQUENCY_THRESHOLD,
  SUBSTANTIVE_WORD_COUNT_THRESHOLD,
  type PassageQualityInput,
} from "@/lib/services/passage-quality";

function input(overrides: Partial<PassageQualityInput> = {}): PassageQualityInput {
  return {
    heading: null,
    text: "The group maintains adequate liquidity headroom and there is no material uncertainty.",
    wordCount: 13,
    hasLanguageSignal: false,
    headingFrequency: 0,
    ...overrides,
  };
}

describe("computePassageQualityFeatures", () => {
  it("assigns the real-corpus word-count bands correctly (substantive threshold)", () => {
    const short = computePassageQualityFeatures(input({ wordCount: SUBSTANTIVE_WORD_COUNT_THRESHOLD - 1 }));
    const long = computePassageQualityFeatures(input({ wordCount: SUBSTANTIVE_WORD_COUNT_THRESHOLD }));
    expect(short.wordCount).toBeLessThan(SUBSTANTIVE_WORD_COUNT_THRESHOLD);
    expect(long.wordCount).toBeGreaterThanOrEqual(SUBSTANTIVE_WORD_COUNT_THRESHOLD);
  });

  it("computes alphabetic token count/ratio, excluding numeric and symbol tokens", () => {
    const features = computePassageQualityFeatures(
      input({ text: "Net Assets 29,037,836 24,976,123 49,135,442 41,079,752", wordCount: 6 }),
    );
    expect(features.alphabeticTokenRatio).toBeLessThan(0.5);
  });

  it("splits heading word count from total word count", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "Remuneration model", text: "Remuneration model AfroCentric's model balances short and long term rewards.", wordCount: 11 }),
    );
    expect(features.headingWordCount).toBe(2);
    expect(features.headingToTotalRatio).toBeCloseTo(2 / 11, 5);
  });

  it("detects a heading-only fragment (text equals heading, real corpus example)", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "Operations (continued)", text: "Operations (continued)", wordCount: 2 }),
    );
    expect(features.isHeadingOnlyFragment).toBe(true);
  });

  it("does not flag a substantive passage sharing its opening words with the heading as heading-only", () => {
    const features = computePassageQualityFeatures(
      input({
        heading: "Remuneration model",
        text: "Remuneration model AfroCentric's remuneration model balances short-term and long-term financial and non-financial rewards to drive a high-performance culture across the group.",
        wordCount: 22,
      }),
    );
    expect(features.isHeadingOnlyFragment).toBe(false);
  });

  it("detects a generic heading via repeated-heading frequency", () => {
    const generic = computePassageQualityFeatures(
      input({ heading: "BACK", text: "BACK", wordCount: 1, headingFrequency: 80 }),
    );
    const distinctive = computePassageQualityFeatures(
      input({ heading: "Foreign currency risk", text: "Foreign currency risk disclosures", wordCount: 3, headingFrequency: 1 }),
    );
    expect(generic.isRepeatedGenericHeading).toBe(true);
    expect(distinctive.isRepeatedGenericHeading).toBe(false);
    expect(REPEATED_HEADING_FREQUENCY_THRESHOLD).toBeGreaterThan(0);
  });

  it('detects "continued" in a heading', () => {
    expect(computePassageQualityFeatures(input({ heading: "Directors' report (cont)", text: "x", wordCount: 1 })).containsContinued).toBe(true);
    expect(computePassageQualityFeatures(input({ heading: "Directors' report continued", text: "x", wordCount: 1 })).containsContinued).toBe(true);
    expect(computePassageQualityFeatures(input({ heading: "Directors' report", text: "x", wordCount: 1 })).containsContinued).toBe(false);
  });

  it("applies the sentence-completeness heuristic (word count + terminal punctuation)", () => {
    const complete = computePassageQualityFeatures(
      input({ text: "The board reviews risk management annually and reports to shareholders.", wordCount: 10 }),
    );
    const incomplete = computePassageQualityFeatures(input({ text: "Board committees and attendance", wordCount: 4 }));
    expect(complete.hasCompleteSentenceHeuristic).toBe(true);
    expect(incomplete.hasCompleteSentenceHeuristic).toBe(false);
  });

  it("computes uppercase-token ratio", () => {
    const features = computePassageQualityFeatures(input({ text: "OVERVIEW OF OPERATIONS AND STRATEGY", wordCount: 5 }));
    expect(features.uppercaseTokenRatio).toBeGreaterThan(0.5);
  });

  it("computes numeric-token ratio", () => {
    const features = computePassageQualityFeatures(input({ text: "Revenue 1,234 5,678 9,012 45.6%", wordCount: 5 }));
    expect(features.numericTokenRatio).toBeGreaterThan(0.5);
  });

  it("handles a null heading without throwing", () => {
    expect(() => computePassageQualityFeatures(input({ heading: null }))).not.toThrow();
    const features = computePassageQualityFeatures(input({ heading: null, wordCount: 5 }));
    expect(features.headingWordCount).toBe(0);
    expect(features.isHeadingOnlyFragment).toBe(false);
    expect(features.isRepeatedGenericHeading).toBe(false);
  });

  it("carries the language-signal flag through unchanged", () => {
    expect(computePassageQualityFeatures(input({ hasLanguageSignal: true })).hasLanguageSignal).toBe(true);
    expect(computePassageQualityFeatures(input({ hasLanguageSignal: false })).hasLanguageSignal).toBe(false);
  });
});

describe("computeQualityAdjustment", () => {
  it("never adjusts a passage at or above the substantive word-count threshold", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "BACK", text: "BACK", wordCount: SUBSTANTIVE_WORD_COUNT_THRESHOLD, headingFrequency: 80 }),
    );
    const adjustment = computeQualityAdjustment(features);
    expect(adjustment.factor).toBe(1);
    expect(adjustment.explanationCode).toBe("NO_QUALITY_ADJUSTMENT");
  });

  it("demotes a short generic heading-only fragment (real corpus example)", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "Operations (continued)", text: "Operations (continued)", wordCount: 2 }),
    );
    const adjustment = computeQualityAdjustment(features);
    expect(adjustment.explanationCode).toBe("HEADING_ONLY_FRAGMENT");
    expect(adjustment.factor).toBeLessThan(1);
    expect(adjustment.factor).toBeGreaterThan(0);
  });

  it("retains a short passage with a real financial-language signal despite fragment-like features", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "Operations (continued)", text: "Operations (continued)", wordCount: 2, hasLanguageSignal: true }),
    );
    const adjustment = computeQualityAdjustment(features);
    expect(adjustment.factor).toBe(1);
    expect(adjustment.explanationCode).toBe("RETAINED_SHORT_FINANCIAL_SENTENCE");
  });

  it("mildly demotes a short passage that is not a clear fragment but lacks a complete sentence", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "Water usage", text: "Water usage E2.1a Megalitres 16 974 kl", wordCount: 8, headingFrequency: 1 }),
    );
    const adjustment = computeQualityAdjustment(features);
    expect(adjustment.explanationCode).not.toBe("NO_QUALITY_ADJUSTMENT");
    expect(adjustment.factor).toBeLessThan(1);
    expect(adjustment.factor).toBeGreaterThan(0);
  });

  it("never returns a factor of exactly 0 (bounded demotion, not deletion)", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "USD", text: "USD", wordCount: 1, headingFrequency: 429 }),
    );
    const adjustment = computeQualityAdjustment(features);
    expect(adjustment.factor).toBeGreaterThan(0);
  });

  it("is deterministic: identical input always yields identical output", () => {
    const features = computePassageQualityFeatures(input({ heading: "BACK", text: "BACK", wordCount: 1, headingFrequency: 80 }));
    const a = computeQualityAdjustment(features);
    const b = computeQualityAdjustment(features);
    expect(a).toEqual(b);
  });

  it("uses a bounded, configurable factor from DEFAULT_QUALITY_ADJUSTMENT_CONFIG", () => {
    expect(DEFAULT_QUALITY_ADJUSTMENT_CONFIG.headingOnlyFragmentFactor).toBeGreaterThan(0);
    expect(DEFAULT_QUALITY_ADJUSTMENT_CONFIG.headingOnlyFragmentFactor).toBeLessThan(1);
  });
});

describe("Milestone 7B.1b numeric-fragment features", () => {
  it("detects a real corpus table-row example as looksLikeTableRow", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "EUR (5% movement) (1,450) 1,450 4 (4)", text: "EUR (5% movement) (1,450) 1,450 4 (4)", wordCount: 8 }),
    );
    expect(features.looksLikeTableRow).toBe(true);
  });

  it("detects a real corpus percentage-only fragment example", () => {
    const features = computePassageQualityFeatures(
      input({
        heading: "Operating margin",
        text: "Operating margin (0.9%) (0.2%) (13.9%)",
        wordCount: 5,
      }),
    );
    expect(features.isPercentageOnlyFragment).toBe(true);
  });

  it("does not flag ordinary prose as a table row or percentage fragment", () => {
    const features = computePassageQualityFeatures(input());
    expect(features.looksLikeTableRow).toBe(false);
    expect(features.isPercentageOnlyFragment).toBe(false);
  });

  it("detects an explanatory verb in prose that discusses a numeric change", () => {
    const features = computePassageQualityFeatures(
      input({ text: "Revenue increased primarily due to higher sales volumes across all regions.", wordCount: 11 }),
    );
    expect(features.hasExplanatoryVerb).toBe(true);
  });

  it("does not detect an explanatory verb in a bare numeric fragment", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "Operating margin", text: "Operating margin (0.9%) (0.2%) (13.9%)", wordCount: 5 }),
    );
    expect(features.hasExplanatoryVerb).toBe(false);
  });

  it("computes a high prose-to-number ratio for ordinary prose", () => {
    const features = computePassageQualityFeatures(input());
    expect(features.proseToNumberRatio).toBeGreaterThan(1);
  });

  it("computes a low prose-to-number ratio for a numeric table row", () => {
    const features = computePassageQualityFeatures(
      input({ text: "1,450 1,450 4 4 (5%) 1,234 5,678", wordCount: 7 }),
    );
    expect(features.proseToNumberRatio).toBeLessThan(1);
  });

  it("passes through hasNearbyContext when supplied, and defaults to null when omitted", () => {
    expect(computePassageQualityFeatures(input({ hasNearbyContext: true })).hasNearbyContext).toBe(true);
    expect(computePassageQualityFeatures(input({ hasNearbyContext: false })).hasNearbyContext).toBe(false);
    expect(computePassageQualityFeatures(input()).hasNearbyContext).toBeNull();
  });
});

describe("computeNumericFragmentSeverity", () => {
  it("returns none for ordinary prose", () => {
    const features = computePassageQualityFeatures(input());
    expect(computeNumericFragmentSeverity(features)).toBe("none");
  });

  it("returns fragment_without_context for a bare table row with no nearby context supplied", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "EUR (5% movement) (1,450) 1,450 4 (4)", text: "EUR (5% movement) (1,450) 1,450 4 (4)", wordCount: 8 }),
    );
    expect(computeNumericFragmentSeverity(features)).toBe("fragment_without_context");
  });

  it("returns fragment_with_context when a nearby explanatory passage was found", () => {
    const features = computePassageQualityFeatures(
      input({
        heading: "EUR (5% movement) (1,450) 1,450 4 (4)",
        text: "EUR (5% movement) (1,450) 1,450 4 (4)",
        wordCount: 8,
        hasNearbyContext: true,
      }),
    );
    expect(computeNumericFragmentSeverity(features)).toBe("fragment_with_context");
  });

  it("returns none when the numeric passage itself contains explanatory prose (same-passage context counts)", () => {
    const features = computePassageQualityFeatures(
      input({ text: "Operating margin declined to 0.9% from 13.9%, driven by higher input costs.", wordCount: 11 }),
    );
    expect(computeNumericFragmentSeverity(features)).toBe("none");
  });

  it("never excludes a numeric fragment outright -- severity classifies, it does not delete", () => {
    const features = computePassageQualityFeatures(
      input({ heading: "Operating margin", text: "Operating margin (0.9%) (0.2%) (13.9%)", wordCount: 5 }),
    );
    expect(["fragment_with_context", "fragment_without_context"]).toContain(computeNumericFragmentSeverity(features));
  });
});
