import { describe, expect, it } from "vitest";
import { classifyFailureStage, probeSufficientSet } from "../../evaluation/qa-failure-attribution";

describe("probeSufficientSet", () => {
  it("is present and in-window when every id is a candidate ranked within the window", () => {
    const rankByPassageId = new Map([["p1", 2], ["p2", 5]]);
    const probe = probeSufficientSet(["p1", "p2"], new Set(["p1", "p2"]), rankByPassageId, 12);
    expect(probe.present).toBe(true);
    expect(probe.inWindow).toBe(true);
    expect(probe.bestRank).toBe(2);
  });

  it("is present but not in-window when a required id ranks beyond the examination window", () => {
    const rankByPassageId = new Map([["p1", 20]]);
    const probe = probeSufficientSet(["p1"], new Set(["p1"]), rankByPassageId, 12);
    expect(probe.present).toBe(true);
    expect(probe.inWindow).toBe(false);
  });

  it("is absent when no id in the set is a candidate at all", () => {
    const probe = probeSufficientSet(["p1"], new Set(["other"]), new Map(), 12);
    expect(probe.present).toBe(false);
    expect(probe.inWindow).toBe(false);
    expect(probe.bestRank).toBeNull();
  });

  it("treats an empty set as absent (no ground truth to recover)", () => {
    const probe = probeSufficientSet([], new Set(["p1"]), new Map([["p1", 1]]), 12);
    expect(probe.present).toBe(false);
  });
});

describe("classifyFailureStage", () => {
  it("classifies a no-answer-expected case matching actual status as PIPELINE_SUCCESS", () => {
    const stage = classifyFailureStage({ expected: "INSUFFICIENT_EVIDENCE", actual: "INSUFFICIENT_EVIDENCE", sufficientSets: [], setProbes: [], recovered: false });
    expect(stage).toBe("PIPELINE_SUCCESS");
  });

  it("classifies a no-answer-expected case with a wrong status as GATE_MISCLASSIFICATION", () => {
    const stage = classifyFailureStage({ expected: "INSUFFICIENT_EVIDENCE", actual: "SUPPORTED", sufficientSets: [], setProbes: [], recovered: false });
    expect(stage).toBe("GATE_MISCLASSIFICATION");
  });

  it("classifies RETRIEVAL_MISS when no alternate sufficient set was even present in candidates", () => {
    const stage = classifyFailureStage({
      expected: "SUPPORTED",
      actual: "INSUFFICIENT_EVIDENCE",
      sufficientSets: [["p1"]],
      setProbes: [{ present: false, inWindow: false, bestRank: null }],
      recovered: false,
    });
    expect(stage).toBe("RETRIEVAL_MISS");
  });

  it("classifies RERANKING_MISS when present but ranked outside the examination window", () => {
    const stage = classifyFailureStage({
      expected: "SUPPORTED",
      actual: "INSUFFICIENT_EVIDENCE",
      sufficientSets: [["p1"]],
      setProbes: [{ present: true, inWindow: false, bestRank: 20 }],
      recovered: false,
    });
    expect(stage).toBe("RERANKING_MISS");
  });

  it("classifies EVIDENCE_SELECTION_MISS when ranked in-window but never selected", () => {
    const stage = classifyFailureStage({
      expected: "SUPPORTED",
      actual: "INSUFFICIENT_EVIDENCE",
      sufficientSets: [["p1"]],
      setProbes: [{ present: true, inWindow: true, bestRank: 3 }],
      recovered: false,
    });
    expect(stage).toBe("EVIDENCE_SELECTION_MISS");
  });

  it("classifies GATE_MISCLASSIFICATION when evidence was recovered but the status is wrong", () => {
    const stage = classifyFailureStage({
      expected: "SUPPORTED",
      actual: "AMBIGUOUS_OR_CONFLICTING",
      sufficientSets: [["p1"]],
      setProbes: [{ present: true, inWindow: true, bestRank: 1 }],
      recovered: true,
    });
    expect(stage).toBe("GATE_MISCLASSIFICATION");
  });

  it("classifies PIPELINE_SUCCESS when evidence was recovered and the status matches", () => {
    const stage = classifyFailureStage({
      expected: "SUPPORTED",
      actual: "SUPPORTED",
      sufficientSets: [["p1"]],
      setProbes: [{ present: true, inWindow: true, bestRank: 1 }],
      recovered: true,
    });
    expect(stage).toBe("PIPELINE_SUCCESS");
  });

  it("never auto-classifies GROUND_TRUTH_AMBIGUITY -- that is always a manual override", () => {
    const stage = classifyFailureStage({ expected: "SUPPORTED", actual: "SUPPORTED", sufficientSets: [], setProbes: [], recovered: false });
    expect(stage).not.toBe("GROUND_TRUTH_AMBIGUITY");
  });
});
