import { describe, expect, it } from "vitest";
import {
  describeNetToneDriver,
  describeTopicChange,
  meetsTopicThreshold,
  relativeLengthChange,
} from "@/lib/services/topic-change";
import { alignmentCaveat, isWeakChangeAttribution } from "@/lib/services/alignment-caveat";
import type { TopicCategoryChange } from "@/lib/domain/comparison";

function change(overrides: Partial<TopicCategoryChange> = {}): TopicCategoryChange {
  return {
    hitsEarlier: 71,
    hitsLater: 55,
    countChangePer1000: -0.9016,
    densityChange: -1.1027,
    topicChange: -0.9016,
    supportingHits: 24,
    opposingHits: 8,
    changeConsistencyRatio: -0.5,
    largestPassageShare: 0.1562,
    ...overrides,
  };
}

describe("meetsTopicThreshold", () => {
  it("applies |value| >= 0.25 in both directions for financial condition and governance", () => {
    expect(meetsTopicThreshold("financial_condition", -0.9016)).toBe(true);
    expect(meetsTopicThreshold("financial_condition", 0.2783)).toBe(true);
    expect(meetsTopicThreshold("governance", -0.1391)).toBe(false);
    expect(meetsTopicThreshold("governance", 0)).toBe(false);
  });

  it("applies increase-only >= 0.75 for uncertainty", () => {
    expect(meetsTopicThreshold("uncertainty", 0.7596)).toBe(true);
    expect(meetsTopicThreshold("uncertainty", -2.0)).toBe(false);
    expect(meetsTopicThreshold("uncertainty", 0.5776)).toBe(false);
  });

  it("is false for a missing value", () => {
    expect(meetsTopicThreshold("financial_condition", null)).toBe(false);
  });
});

describe("describeTopicChange", () => {
  it("explains a flat count as no topic change", () => {
    expect(describeTopicChange(change({ hitsEarlier: 152, hitsLater: 152, countChangePer1000: 0, topicChange: 0 }))).toMatch(
      /did not change/,
    );
  });

  it("explains disagreeing legs as report-length driven", () => {
    expect(describeTopicChange(change({ hitsEarlier: 117, hitsLater: 67, countChangePer1000: -1.35, densityChange: 0.15, topicChange: 0 }))).toMatch(
      /opposite directions/,
    );
  });

  it("explains agreeing legs", () => {
    expect(describeTopicChange(change())).toMatch(/Both the word count and the word density fell/);
  });

  it("returns null when inputs are missing", () => {
    expect(describeTopicChange(change({ topicChange: null }))).toBeNull();
  });
});

describe("relativeLengthChange", () => {
  it("is relative to the pair-average length", () => {
    expect(relativeLengthChange(1000, 3000)).toBeCloseTo(1.0);
    expect(relativeLengthChange(null, 10)).toBeNull();
  });
});

describe("describeNetToneDriver", () => {
  it("attributes a decline to fewer positive words when that component dominates", () => {
    expect(describeNetToneDriver(-3.0, -2.5, 0.5)).toBe("Driven mainly by fewer positive words.");
  });

  it("attributes a decline to more negative words when that component dominates", () => {
    expect(describeNetToneDriver(-3.0, -0.5, 2.5)).toBe("Driven mainly by more negative words.");
  });

  it("describes a rise symmetrically", () => {
    expect(describeNetToneDriver(2.0, 0.5, -1.5)).toBe("Driven mainly by fewer negative words.");
  });

  it("returns null for zero or missing change", () => {
    expect(describeNetToneDriver(0, 1, 1)).toBeNull();
    expect(describeNetToneDriver(-1, null, 1)).toBeNull();
  });
});

describe("alignment caveat", () => {
  it("flags NEW/REMOVED/SUBSTANTIALLY_MODIFIED passages with weak confidence as possibly moved", () => {
    expect(isWeakChangeAttribution("NEW", "LOW")).toBe(true);
    expect(isWeakChangeAttribution("REMOVED", "NEEDS_REVIEW")).toBe(true);
    expect(isWeakChangeAttribution("SUBSTANTIALLY_MODIFIED", "LOW")).toBe(true);
    expect(alignmentCaveat("NEW", "LOW")).toMatch(/^Possibly moved or restructured/);
  });

  it("does not flag well-aligned or unchanged passages", () => {
    expect(isWeakChangeAttribution("NEW", "HIGH")).toBe(false);
    expect(isWeakChangeAttribution("UNCHANGED", "LOW")).toBe(false);
    expect(isWeakChangeAttribution(null, "LOW")).toBe(false);
    expect(alignmentCaveat("REMOVED", "MEDIUM")).toBeNull();
  });
});
