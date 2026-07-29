import { describe, expect, it } from "vitest";
import { QUALITY_TIER_ORDER, meetsMinimumQuality } from "@/lib/domain/quality";
import { rawQualityFromLabel } from "@/lib/formatting/labels";

describe("QUALITY_TIER_ORDER", () => {
  it("orders the four tiers worst-to-best: FAILED < NEEDS_REVIEW < USABLE < GOOD", () => {
    expect(QUALITY_TIER_ORDER.FAILED).toBeLessThan(QUALITY_TIER_ORDER.NEEDS_REVIEW);
    expect(QUALITY_TIER_ORDER.NEEDS_REVIEW).toBeLessThan(QUALITY_TIER_ORDER.USABLE);
    expect(QUALITY_TIER_ORDER.USABLE).toBeLessThan(QUALITY_TIER_ORDER.GOOD);
  });
});

describe("meetsMinimumQuality", () => {
  it("always passes when no minimum is set", () => {
    expect(meetsMinimumQuality(null, null)).toBe(true);
    expect(meetsMinimumQuality("FAILED", null)).toBe(true);
  });

  it("a null raw tier never satisfies a set minimum", () => {
    expect(meetsMinimumQuality(null, "GOOD")).toBe(false);
  });

  it("passes when raw is exactly the minimum", () => {
    expect(meetsMinimumQuality("USABLE", "USABLE")).toBe(true);
  });

  it("passes when raw exceeds the minimum", () => {
    expect(meetsMinimumQuality("GOOD", "NEEDS_REVIEW")).toBe(true);
  });

  it("fails when raw is below the minimum", () => {
    expect(meetsMinimumQuality("NEEDS_REVIEW", "GOOD")).toBe(false);
  });
});

describe("rawQualityFromLabel", () => {
  it("resolves a report-side label to its raw tier", () => {
    expect(rawQualityFromLabel("report-side", "Analysis ready")).toBe("GOOD");
    expect(rawQualityFromLabel("report-side", "Review recommended")).toBe("NEEDS_REVIEW");
  });

  it("resolves an alignment-change label to its raw tier, distinct vocabulary from report-side", () => {
    expect(rawQualityFromLabel("alignment-change", "Strong attribution")).toBe("GOOD");
    expect(rawQualityFromLabel("alignment-change", "Attribution uncertain")).toBe("NEEDS_REVIEW");
  });

  it("returns null for a label that doesn't belong to the given dimension's vocabulary", () => {
    expect(rawQualityFromLabel("alignment-change", "Analysis ready")).toBeNull();
  });

  it("returns null for a completely unrecognized label", () => {
    expect(rawQualityFromLabel("report-side", "Not a real label")).toBeNull();
  });
});
