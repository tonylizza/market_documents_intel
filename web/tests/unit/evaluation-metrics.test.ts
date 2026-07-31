import { describe, expect, it } from "vitest";
import {
  aggregateMetrics,
  computeCaseMetrics,
  irrelevantShortFragmentRateAtK,
  meanOf,
  ndcgAtK,
  precisionAtK,
  rateAtOrAboveThreshold,
  rateBelowThreshold,
  recallAtK,
  reciprocalRank,
  shortFragmentRateAtK,
  substantivePrecisionAtK,
} from "@/evaluation/metrics";

describe("recallAtK", () => {
  it("returns 1 when there are no relevant ids (nothing to miss)", () => {
    expect(recallAtK(["a", "b"], new Set(), 5)).toBe(1);
  });

  it("computes the fraction of relevant ids found in the top k", () => {
    expect(recallAtK(["a", "b", "c"], new Set(["a", "c", "z"]), 3)).toBeCloseTo(2 / 3, 10);
  });

  it("only counts hits within the top k window", () => {
    expect(recallAtK(["z", "a"], new Set(["a"]), 1)).toBe(0);
    expect(recallAtK(["z", "a"], new Set(["a"]), 2)).toBe(1);
  });
});

describe("precisionAtK", () => {
  it("returns 0 for an empty ranking", () => {
    expect(precisionAtK([], new Set(["a"]), 5)).toBe(0);
  });

  it("computes hits divided by k when the ranking has at least k items", () => {
    expect(precisionAtK(["a", "b", "c", "d", "e"], new Set(["a", "c"]), 5)).toBeCloseTo(2 / 5, 10);
  });
});

describe("reciprocalRank", () => {
  it("returns 1/rank of the first relevant hit", () => {
    expect(reciprocalRank(["z", "a", "b"], new Set(["a"]))).toBeCloseTo(1 / 2, 10);
  });

  it("returns 0 when no relevant id appears at all", () => {
    expect(reciprocalRank(["z", "y"], new Set(["a"]))).toBe(0);
  });
});

describe("ndcgAtK", () => {
  it("returns 1.0 for a perfectly-ordered ranking", () => {
    const graded = new Map([
      ["a", "highly_relevant" as const],
      ["b", "relevant" as const],
    ]);
    expect(ndcgAtK(["a", "b"], graded, 10)).toBeCloseTo(1, 10);
  });

  it("penalizes a reversed ranking", () => {
    const graded = new Map([
      ["a", "highly_relevant" as const],
      ["b", "relevant" as const],
    ]);
    const perfect = ndcgAtK(["a", "b"], graded, 10);
    const reversed = ndcgAtK(["b", "a"], graded, 10);
    expect(reversed).toBeLessThan(perfect);
  });

  it("returns 0 when there is no graded relevance data", () => {
    expect(ndcgAtK(["a", "b"], new Map(), 10)).toBe(0);
  });
});

describe("computeCaseMetrics", () => {
  it("computes all metrics for a case with binary relevance only", () => {
    const metrics = computeCaseMetrics(["a", "b", "c"], ["a"]);
    expect(metrics.recallAt5).toBe(1);
    expect(metrics.mrr).toBe(1);
    expect(metrics.ndcgAt10).toBeNull();
  });

  it("computes ndcg when graded relevance is provided", () => {
    const graded = new Map([["a", "highly_relevant" as const]]);
    const metrics = computeCaseMetrics(["a", "b"], ["a"], graded);
    expect(metrics.ndcgAt10).toBeCloseTo(1, 10);
  });
});

describe("shortFragmentRateAtK", () => {
  it("computes the fraction of the top-k that are fragments", () => {
    expect(shortFragmentRateAtK([true, false, true, false, false], 5)).toBeCloseTo(0.4, 10);
  });

  it("returns 0 for an empty ranking", () => {
    expect(shortFragmentRateAtK([], 5)).toBe(0);
  });
});

describe("irrelevantShortFragmentRateAtK", () => {
  it("counts only fragments that are also irrelevant", () => {
    const ranked = ["a", "b", "c", "d"];
    const isFragment = new Set(["a", "b"]);
    const relevant = new Set(["b"]); // b is a fragment but genuinely relevant -- not counted
    expect(irrelevantShortFragmentRateAtK(ranked, isFragment, relevant, 4)).toBeCloseTo(0.25, 10);
  });
});

describe("substantivePrecisionAtK", () => {
  it("excludes relevant-but-fragmentary hits from precision credit", () => {
    const ranked = ["a", "b", "c"];
    const relevant = new Set(["a", "b"]);
    const isFragment = new Set(["b"]);
    // Only "a" counts: relevant and not a fragment.
    expect(substantivePrecisionAtK(ranked, relevant, isFragment, 3)).toBeCloseTo(1 / 3, 10);
  });
});

describe("rateAtOrAboveThreshold / rateBelowThreshold", () => {
  it("computes the false-strong-match rate for no-answer similarities", () => {
    expect(rateAtOrAboveThreshold([0.6, 0.8, 0.5], 0.7)).toBeCloseTo(1 / 3, 10);
  });

  it("computes the answerable-query suppression rate", () => {
    expect(rateBelowThreshold([0.6, 0.8, 0.5], 0.7)).toBeCloseTo(2 / 3, 10);
  });

  it("returns 0 for an empty similarity list", () => {
    expect(rateAtOrAboveThreshold([], 0.7)).toBe(0);
    expect(rateBelowThreshold([], 0.7)).toBe(0);
  });
});

describe("meanOf / aggregateMetrics", () => {
  it("meanOf returns 0 for an empty array", () => {
    expect(meanOf([])).toBe(0);
  });

  it("aggregateMetrics averages across cases and handles missing ndcg gracefully", () => {
    const perCase = [
      computeCaseMetrics(["a"], ["a"]),
      computeCaseMetrics(["z"], ["a"]),
    ];
    const aggregate = aggregateMetrics(perCase);
    expect(aggregate.caseCount).toBe(2);
    expect(aggregate.meanRecallAt10).toBeCloseTo(0.5, 10);
    expect(aggregate.meanNdcgAt10).toBeNull();
  });
});
