import { describe, expect, it } from "vitest";
import { decideDefaultSearchMode } from "@/evaluation/default-mode-rule";
import type { AggregateMetrics } from "@/evaluation/metrics";

function metrics(overrides: Partial<AggregateMetrics> = {}): AggregateMetrics {
  return {
    caseCount: 10,
    meanRecallAt5: 0.5,
    meanRecallAt10: 0.5,
    meanPrecisionAt5: 0.2,
    meanMrr: 0.3,
    meanNdcgAt10: 0.3,
    ...overrides,
  };
}

describe("decideDefaultSearchMode", () => {
  it("keeps keyword as the default when keyword clearly outperforms hybrid", () => {
    const decision = decideDefaultSearchMode({
      keyword: metrics({ meanNdcgAt10: 0.4, meanRecallAt10: 0.6 }),
      hybrid: metrics({ meanNdcgAt10: 0.2, meanRecallAt10: 0.5 }),
    });
    expect(decision.mode).toBe("keyword");
  });

  it("selects hybrid when it is clearly better with no keyword recall regression", () => {
    const decision = decideDefaultSearchMode({
      keyword: metrics({ meanNdcgAt10: 0.2, meanRecallAt10: 0.5 }),
      hybrid: metrics({ meanNdcgAt10: 0.4, meanRecallAt10: 0.6 }),
    });
    expect(decision.mode).toBe("hybrid");
  });

  it("selects hybrid when effectively tied on nDCG@10 and recall does not regress", () => {
    const decision = decideDefaultSearchMode({
      keyword: metrics({ meanNdcgAt10: 0.3, meanRecallAt10: 0.5 }),
      hybrid: metrics({ meanNdcgAt10: 0.302, meanRecallAt10: 0.5 }),
    });
    expect(decision.mode).toBe("hybrid");
  });

  it("keeps keyword when hybrid ties on nDCG@10 but regresses keyword recall@10", () => {
    const decision = decideDefaultSearchMode({
      keyword: metrics({ meanNdcgAt10: 0.3, meanRecallAt10: 0.6 }),
      hybrid: metrics({ meanNdcgAt10: 0.3, meanRecallAt10: 0.4 }),
    });
    expect(decision.mode).toBe("keyword");
  });

  it("falls back to MRR when nDCG@10 data is unavailable", () => {
    const decision = decideDefaultSearchMode({
      keyword: metrics({ meanNdcgAt10: null, meanMrr: 0.4, meanRecallAt10: 0.5 }),
      hybrid: metrics({ meanNdcgAt10: null, meanMrr: 0.2, meanRecallAt10: 0.5 }),
    });
    expect(decision.mode).toBe("keyword");
  });

  it("matches the real Milestone 7B.1 evaluation result: keyword remains the default", () => {
    // Real aggregate figures from evaluation/results/publication_retrieval_evaluation.csv
    const decision = decideDefaultSearchMode({
      keyword: metrics({ meanNdcgAt10: 0.186, meanRecallAt10: 0.587 }),
      hybrid: metrics({ meanNdcgAt10: 0.126, meanRecallAt10: 0.609 }),
    });
    expect(decision.mode).toBe("keyword");
  });
});
