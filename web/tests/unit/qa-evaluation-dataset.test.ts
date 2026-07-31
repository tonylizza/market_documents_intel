import { describe, expect, it } from "vitest";
import { QA_EVALUATION_DATASET } from "@/evaluation/qa-dataset";

describe("QA_EVALUATION_DATASET", () => {
  it("has at least 60 cases (Milestone 7B.1b minimum)", () => {
    expect(QA_EVALUATION_DATASET.length).toBeGreaterThanOrEqual(60);
  });

  it("has unique case ids", () => {
    const ids = QA_EVALUATION_DATASET.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("every case has a non-empty question and a documented rationale", () => {
    for (const c of QA_EVALUATION_DATASET) {
      expect(c.question.trim().length, c.id).toBeGreaterThan(0);
      expect(c.notes.trim().length, c.id).toBeGreaterThan(0);
    }
  });

  it("covers all four answerability classes", () => {
    const present = new Set(QA_EVALUATION_DATASET.map((c) => c.expectedAnswerability));
    for (const cls of ["SUPPORTED", "PARTIALLY_SUPPORTED", "INSUFFICIENT_EVIDENCE", "AMBIGUOUS_OR_CONFLICTING"] as const) {
      expect(present.has(cls), `missing answerability class: ${cls}`).toBe(true);
    }
  });

  it("has at least 10 INSUFFICIENT_EVIDENCE (no-answer) cases", () => {
    const noAnswer = QA_EVALUATION_DATASET.filter((c) => c.expectedAnswerability === "INSUFFICIENT_EVIDENCE");
    expect(noAnswer.length).toBeGreaterThanOrEqual(10);
  });

  it("has at least 5 AMBIGUOUS_OR_CONFLICTING cases", () => {
    const ambiguous = QA_EVALUATION_DATASET.filter((c) => c.expectedAnswerability === "AMBIGUOUS_OR_CONFLICTING");
    expect(ambiguous.length).toBeGreaterThanOrEqual(5);
  });

  it("has at least 5 PARTIALLY_SUPPORTED cases", () => {
    const partial = QA_EVALUATION_DATASET.filter((c) => c.expectedAnswerability === "PARTIALLY_SUPPORTED");
    expect(partial.length).toBeGreaterThanOrEqual(5);
  });

  it("has at least 3 numeric-fragment-trap cases", () => {
    const numericTraps = QA_EVALUATION_DATASET.filter((c) => c.numericFragmentTrapPassageIds && c.numericFragmentTrapPassageIds.length > 0);
    expect(numericTraps.length).toBeGreaterThanOrEqual(3);
  });

  it("has at least 3 short-heading-trap cases", () => {
    const headingTraps = QA_EVALUATION_DATASET.filter((c) => c.shortHeadingTrapPassageIds && c.shortHeadingTrapPassageIds.length > 0);
    expect(headingTraps.length).toBeGreaterThanOrEqual(3);
  });

  it("SUPPORTED and PARTIALLY_SUPPORTED cases have at least one non-empty minimum-sufficient evidence set", () => {
    const shouldHaveEvidence = QA_EVALUATION_DATASET.filter(
      (c) => c.expectedAnswerability === "SUPPORTED" || c.expectedAnswerability === "PARTIALLY_SUPPORTED",
    );
    for (const c of shouldHaveEvidence) {
      expect(c.minimumSufficientEvidenceSets.length, c.id).toBeGreaterThan(0);
      for (const set of c.minimumSufficientEvidenceSets) {
        expect(set.length, c.id).toBeGreaterThan(0);
      }
    }
  });

  it("INSUFFICIENT_EVIDENCE and AMBIGUOUS_OR_CONFLICTING cases declare no minimum-sufficient evidence set", () => {
    const shouldHaveNone = QA_EVALUATION_DATASET.filter(
      (c) => c.expectedAnswerability === "INSUFFICIENT_EVIDENCE" || c.expectedAnswerability === "AMBIGUOUS_OR_CONFLICTING",
    );
    for (const c of shouldHaveNone) {
      expect(c.minimumSufficientEvidenceSets, c.id).toEqual([]);
    }
  });

  it("non-SUPPORTED cases declare at least one expected gate reason code", () => {
    const nonSupported = QA_EVALUATION_DATASET.filter((c) => c.expectedAnswerability !== "SUPPORTED");
    for (const c of nonSupported) {
      expect(c.expectedGateReasonCodes?.length ?? 0, c.id).toBeGreaterThan(0);
    }
  });

  it("trap passage ids never overlap with a case's own minimum-sufficient evidence ids", () => {
    for (const c of QA_EVALUATION_DATASET) {
      const sufficient = new Set(c.minimumSufficientEvidenceSets.flat());
      const traps = [...(c.unsupportedTrapPassageIds ?? []), ...(c.numericFragmentTrapPassageIds ?? []), ...(c.shortHeadingTrapPassageIds ?? [])];
      for (const trapId of traps) {
        expect(sufficient.has(trapId), `${c.id}: trap id ${trapId} also listed as sufficient evidence`).toBe(false);
      }
    }
  });

  it("relevance judgments were not derived from this pipeline's own output (no score/rank fields on cases)", () => {
    for (const c of QA_EVALUATION_DATASET) {
      expect(c).not.toHaveProperty("relevanceScore");
      expect(c).not.toHaveProperty("gateStatus");
    }
  });

  it("every referenced passage id looks like a real UUID, not a placeholder", () => {
    const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    for (const c of QA_EVALUATION_DATASET) {
      const allIds = [
        ...c.minimumSufficientEvidenceSets.flat(),
        ...(c.acceptableAdditionalPassageIds ?? []),
        ...(c.unsupportedTrapPassageIds ?? []),
        ...(c.numericFragmentTrapPassageIds ?? []),
        ...(c.shortHeadingTrapPassageIds ?? []),
      ];
      for (const id of allIds) {
        expect(uuidPattern.test(id), `${c.id}: ${id} is not a valid UUID`).toBe(true);
      }
    }
  });
});
