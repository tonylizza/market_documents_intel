import { describe, expect, it } from "vitest";
import {
  accuracyByGroup,
  answerableQuestionCoverage,
  classificationAccuracyFor,
  correctAbstentionRate,
  duplicateEvidenceRate,
  evidencePrecisionAtK,
  evidenceRecallAtK,
  meanOf,
  noAnswerFalseSupportRate,
  numericFragmentMisuseRate,
  percentile,
  rateOf,
  recoveredMinimumSufficientSet,
  unsupportedEvidenceRate,
  type AnswerabilityOutcome,
} from "@/evaluation/qa-metrics";

describe("evidencePrecisionAtK / evidenceRecallAtK", () => {
  it("computes precision as hits over k", () => {
    expect(evidencePrecisionAtK(["a", "b", "c"], new Set(["a", "c"]), 3)).toBeCloseTo(2 / 3, 10);
  });

  it("returns 0 precision for an empty selection", () => {
    expect(evidencePrecisionAtK([], new Set(["a"]), 5)).toBe(0);
  });

  it("returns full recall when there are no relevant ids to miss", () => {
    expect(evidenceRecallAtK(["a"], new Set(), 5)).toBe(1);
  });

  it("computes recall as fraction of relevant ids found in top k", () => {
    expect(evidenceRecallAtK(["a", "b"], new Set(["a", "b", "c"]), 5)).toBeCloseTo(2 / 3, 10);
  });
});

describe("recoveredMinimumSufficientSet", () => {
  it("returns true when the selected set fully contains one alternate sufficient set", () => {
    expect(recoveredMinimumSufficientSet(["a", "b", "c"], [["a", "b"]])).toBe(true);
  });

  it("returns true when only a later alternate set is fully recovered", () => {
    expect(recoveredMinimumSufficientSet(["x", "y"], [["a", "b"], ["x", "y"]])).toBe(true);
  });

  it("returns false when no alternate set is fully covered", () => {
    expect(recoveredMinimumSufficientSet(["a"], [["a", "b"]])).toBe(false);
  });

  it("returns false when there are no sufficient sets at all (a no-answer case)", () => {
    expect(recoveredMinimumSufficientSet(["a", "b"], [])).toBe(false);
  });
});

describe("meanOf / rateOf", () => {
  it("meanOf returns 0 for an empty array", () => {
    expect(meanOf([])).toBe(0);
  });

  it("rateOf computes the fraction of true flags", () => {
    expect(rateOf([true, true, false, false])).toBe(0.5);
  });
});

describe("correctAbstentionRate / noAnswerFalseSupportRate", () => {
  const outcomes: AnswerabilityOutcome[] = [
    { caseId: "a", expected: "INSUFFICIENT_EVIDENCE", actual: "INSUFFICIENT_EVIDENCE" },
    { caseId: "b", expected: "INSUFFICIENT_EVIDENCE", actual: "SUPPORTED" },
    { caseId: "c", expected: "SUPPORTED", actual: "SUPPORTED" },
  ];

  it("computes correct abstention rate only over no-answer-expected cases", () => {
    expect(correctAbstentionRate(outcomes)).toBeCloseTo(0.5, 10);
  });

  it("computes the false-support rate as the fraction of no-answer cases that were wrongly SUPPORTED", () => {
    expect(noAnswerFalseSupportRate(outcomes)).toBeCloseTo(0.5, 10);
  });

  it("returns 1.0 correct abstention and 0 false-support when there are no no-answer cases", () => {
    const onlySupported: AnswerabilityOutcome[] = [{ caseId: "a", expected: "SUPPORTED", actual: "SUPPORTED" }];
    expect(correctAbstentionRate(onlySupported)).toBe(1);
    expect(noAnswerFalseSupportRate(onlySupported)).toBe(0);
  });
});

describe("classificationAccuracyFor", () => {
  it("computes accuracy scoped to a single expected class", () => {
    const outcomes: AnswerabilityOutcome[] = [
      { caseId: "a", expected: "PARTIALLY_SUPPORTED", actual: "PARTIALLY_SUPPORTED" },
      { caseId: "b", expected: "PARTIALLY_SUPPORTED", actual: "SUPPORTED" },
      { caseId: "c", expected: "SUPPORTED", actual: "SUPPORTED" },
    ];
    expect(classificationAccuracyFor(outcomes, "PARTIALLY_SUPPORTED")).toBeCloseTo(0.5, 10);
  });

  it("returns 1.0 when no cases of that class exist (vacuously correct)", () => {
    const outcomes: AnswerabilityOutcome[] = [{ caseId: "a", expected: "SUPPORTED", actual: "SUPPORTED" }];
    expect(classificationAccuracyFor(outcomes, "AMBIGUOUS_OR_CONFLICTING")).toBe(1);
  });
});

describe("answerableQuestionCoverage / unsupportedEvidenceRate / duplicateEvidenceRate / numericFragmentMisuseRate", () => {
  it("computes answerable-question coverage as the recovery rate", () => {
    expect(answerableQuestionCoverage([true, true, false, true])).toBeCloseTo(0.75, 10);
  });

  it("computes unsupported-evidence rate from per-case trap-selection flags", () => {
    expect(unsupportedEvidenceRate([true, false, false, false])).toBeCloseTo(0.25, 10);
  });

  it("computes duplicate-evidence rate from per-case duplicate flags", () => {
    expect(duplicateEvidenceRate([false, false, false])).toBe(0);
  });

  it("computes numeric-fragment misuse rate from per-case flags", () => {
    expect(numericFragmentMisuseRate([true, true, false, false])).toBeCloseTo(0.5, 10);
  });
});

describe("accuracyByGroup", () => {
  it("groups outcomes and computes per-group accuracy", () => {
    const outcomes = [
      { caseId: "a", expected: "SUPPORTED" as const, actual: "SUPPORTED" as const, group: "descriptive" },
      { caseId: "b", expected: "SUPPORTED" as const, actual: "PARTIALLY_SUPPORTED" as const, group: "descriptive" },
      { caseId: "c", expected: "SUPPORTED" as const, actual: "SUPPORTED" as const, group: "comparative" },
    ];
    const grouped = accuracyByGroup(outcomes);
    const descriptive = grouped.find((g) => g.group === "descriptive")!;
    const comparative = grouped.find((g) => g.group === "comparative")!;
    expect(descriptive.caseCount).toBe(2);
    expect(descriptive.accuracy).toBeCloseTo(0.5, 10);
    expect(comparative.accuracy).toBe(1);
  });
});

describe("percentile", () => {
  it("computes the requested percentile of a sorted value list", () => {
    expect(percentile([10, 20, 30, 40, 50], 50)).toBe(30);
  });

  it("returns 0 for an empty list", () => {
    expect(percentile([], 90)).toBe(0);
  });
});
