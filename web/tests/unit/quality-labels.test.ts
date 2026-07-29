import { describe, expect, it } from "vitest";
import { qualityVisualVariant, isRawQuality } from "@/lib/domain/quality";
import { resolveQualityLabel } from "@/lib/formatting/labels";

describe("resolveQualityLabel", () => {
  it("prefers the database-supplied label when present", () => {
    expect(resolveQualityLabel("report-side", "NEEDS_REVIEW", "A custom label")).toBe("A custom label");
  });

  it("falls back to the report-side vocabulary when label is missing", () => {
    expect(resolveQualityLabel("report-side", "NEEDS_REVIEW", null)).toBe("Review recommended");
    expect(resolveQualityLabel("report-side", "GOOD", null)).toBe("Analysis ready");
  });

  it("falls back to the alignment-change vocabulary, distinct from report-side", () => {
    expect(resolveQualityLabel("alignment-change", "NEEDS_REVIEW", null)).toBe("Attribution uncertain");
    expect(resolveQualityLabel("alignment-change", "FAILED", null)).toBe("Attribution unavailable");
  });

  it("falls back to the disclosure-change vocabulary (same wording as report-side)", () => {
    expect(resolveQualityLabel("disclosure-change", "NEEDS_REVIEW", null)).toBe("Review recommended");
  });

  it("the same raw tier maps to different text across dimensions", () => {
    const reportSide = resolveQualityLabel("report-side", "NEEDS_REVIEW", null);
    const alignmentChange = resolveQualityLabel("alignment-change", "NEEDS_REVIEW", null);
    expect(reportSide).not.toBe(alignmentChange);
  });

  it("returns null when both raw and label are absent", () => {
    expect(resolveQualityLabel("report-side", null, null)).toBeNull();
  });
});

describe("qualityVisualVariant", () => {
  it("maps every known tier to a distinct variant", () => {
    expect(qualityVisualVariant("GOOD")).toBe("good");
    expect(qualityVisualVariant("USABLE")).toBe("usable");
    expect(qualityVisualVariant("NEEDS_REVIEW")).toBe("needs-review");
    expect(qualityVisualVariant("FAILED")).toBe("failed");
  });

  it("maps null to unknown, never fabricating a tier", () => {
    expect(qualityVisualVariant(null)).toBe("unknown");
  });
});

describe("isRawQuality", () => {
  it("accepts known tiers and rejects everything else", () => {
    expect(isRawQuality("GOOD")).toBe(true);
    expect(isRawQuality("BOGUS")).toBe(false);
    expect(isRawQuality(null)).toBe(false);
    expect(isRawQuality(undefined)).toBe(false);
  });
});
