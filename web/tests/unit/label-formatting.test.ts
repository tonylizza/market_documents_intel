import { describe, expect, it } from "vitest";
import { buildDataCoverageNote, formatCategoryLabel, formatPassageStatusLabel } from "@/lib/formatting/labels";

describe("formatCategoryLabel", () => {
  it("title-cases an ordinary snake_case category", () => {
    expect(formatCategoryLabel("uncertainty")).toBe("Uncertainty");
    expect(formatCategoryLabel("litigious")).toBe("Litigious");
  });

  it("uses the override for financial_condition rather than a literal split", () => {
    expect(formatCategoryLabel("financial_condition")).toBe("Financial condition");
  });

  it("formats strong_modal/weak_modal via their overrides", () => {
    expect(formatCategoryLabel("strong_modal")).toBe("Strong modal");
    expect(formatCategoryLabel("weak_modal")).toBe("Weak modal");
  });

  it("falls back to a generic title-case split for an unrecognized category", () => {
    expect(formatCategoryLabel("some_future_category")).toBe("Some Future Category");
  });
});

describe("formatPassageStatusLabel", () => {
  it("formats every known alignment-status value", () => {
    expect(formatPassageStatusLabel("NEW")).toBe("New");
    expect(formatPassageStatusLabel("SUBSTANTIALLY_MODIFIED")).toBe("Substantially modified");
    expect(formatPassageStatusLabel("UNCHANGED")).toBe("Unchanged");
    expect(formatPassageStatusLabel("AMBIGUOUS")).toBe("Ambiguous");
  });

  it("falls back to the raw value for an unrecognized status rather than throwing", () => {
    expect(formatPassageStatusLabel("SOMETHING_ELSE")).toBe("SOMETHING_ELSE");
  });
});

describe("buildDataCoverageNote", () => {
  it("includes the year range and singular/plural counts", () => {
    expect(buildDataCoverageNote(9, 8, "2016-06-30", "2024-06-30")).toBe(
      "Coverage spans 2016–2024 across 9 reports and 8 comparisons.",
    );
  });

  it("uses singular wording for exactly one report/comparison", () => {
    expect(buildDataCoverageNote(1, 0, "2024-06-30", "2024-06-30")).toBe(
      "Coverage spans 2024–2024 across 1 report and 0 comparisons.",
    );
  });

  it("falls back to a date-free note when period ends are missing", () => {
    expect(buildDataCoverageNote(2, 1, null, null)).toBe("Coverage: 2 reports, 1 comparison.");
  });
});
