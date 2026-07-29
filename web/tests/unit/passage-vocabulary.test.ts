import { describe, expect, it } from "vitest";
import {
  ALIGNMENT_STATUSES,
  CONFIDENCE_LEVELS,
  PASSAGE_TYPES,
  REPORT_SIDES,
  formatAlignmentStatusLabel,
  formatAlignmentTypeLabel,
  formatConfidenceLabel,
  formatPassageTypeLabel,
  formatReportSideLabel,
  formatStructuredContentCategoryLabel,
} from "@/lib/config/passage-vocabulary";

describe("controlled-vocabulary label mapping", () => {
  it("never renders a raw SCREAMING_SNAKE_CASE alignment-status value", () => {
    for (const status of ALIGNMENT_STATUSES) {
      const label = formatAlignmentStatusLabel(status);
      expect(label).not.toBe(status);
      expect(label).not.toMatch(/^[A-Z_]+$/);
    }
  });

  it("maps every confidence tier to a plain-language label", () => {
    for (const confidence of CONFIDENCE_LEVELS) {
      expect(formatConfidenceLabel(confidence)).not.toBe(confidence);
    }
  });

  it("maps every passage type to a plain-language label", () => {
    for (const type of PASSAGE_TYPES) {
      expect(formatPassageTypeLabel(type)).not.toBe(type);
    }
  });

  it("maps every report side to a plain-language label", () => {
    for (const side of REPORT_SIDES) {
      expect(formatReportSideLabel(side)).not.toBe(side);
    }
  });

  it("maps alignment type", () => {
    expect(formatAlignmentTypeLabel("ONE_TO_ONE")).toBe("Matched one-to-one");
  });

  it("returns null (not a fabricated label) for an unrecognized structured-content category", () => {
    expect(formatStructuredContentCategoryLabel("list_content")).not.toBeNull();
    expect(formatStructuredContentCategoryLabel("some_future_unrecognized_category")).toBeNull();
  });
});
