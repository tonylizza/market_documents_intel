import { describe, expect, it } from "vitest";
import { passageLanguageSignalRowSchema, passageSearchRowSchema } from "@/lib/schemas/passage";

const VALID_SEARCH_ROW = {
  passage_id: "p1",
  passage_comparison_id: "pc1",
  report_comparison_id: "rc1",
  company_id: "c1",
  company_ticker: "ACT",
  company_name: "Acme",
  report_id: "r1",
  report_period_end: "2024-06-30",
  report_side: "LATER",
  earlier_period_end: "2023-06-30",
  later_period_end: "2024-06-30",
  heading: "Liquidity",
  passage_type: "HEADING_WITH_BODY",
  structured_content_category: null,
  first_page_number: 1,
  last_page_number: 1,
  word_count: 10,
  primary_narrative_eligible: true,
  feature_eligible: true,
  text: "text",
  alignment_status: "UNCHANGED",
  alignment_type: "ONE_TO_ONE",
  confidence: "HIGH",
  confidence_label: "High confidence",
  collision_flag: false,
  split_merge_flag: false,
  rank: 0.5,
};

describe("passageSearchRowSchema", () => {
  it("accepts a well-formed row", () => {
    expect(passageSearchRowSchema.safeParse(VALID_SEARCH_ROW).success).toBe(true);
  });

  it("tolerates a report-only passage (every alignment field null)", () => {
    const row = {
      ...VALID_SEARCH_ROW,
      passage_comparison_id: null,
      report_comparison_id: null,
      report_side: null,
      earlier_period_end: null,
      later_period_end: null,
      alignment_status: null,
      alignment_type: null,
      confidence: null,
      confidence_label: null,
      collision_flag: null,
      split_merge_flag: null,
      rank: null,
    };
    expect(passageSearchRowSchema.safeParse(row).success).toBe(true);
  });

  it("tolerates a null heading (a real, published condition)", () => {
    expect(passageSearchRowSchema.safeParse({ ...VALID_SEARCH_ROW, heading: null }).success).toBe(true);
  });

  it("rejects a row with an unrecognized alignment_status (not silently coerced)", () => {
    const result = passageSearchRowSchema.safeParse({ ...VALID_SEARCH_ROW, alignment_status: "NOT_A_REAL_STATUS" });
    expect(result.success).toBe(false);
  });

  it("rejects a row missing a required field", () => {
    const withoutId: Partial<typeof VALID_SEARCH_ROW> = { ...VALID_SEARCH_ROW };
    delete withoutId.passage_id;
    expect(passageSearchRowSchema.safeParse(withoutId).success).toBe(false);
  });

  it("rejects a row with the wrong type for a numeric field", () => {
    expect(passageSearchRowSchema.safeParse({ ...VALID_SEARCH_ROW, word_count: "ten" }).success).toBe(false);
  });
});

describe("passageLanguageSignalRowSchema", () => {
  it("accepts a core-category row (subcategory null)", () => {
    const row = {
      report_side: "EARLIER",
      category: "uncertainty",
      subcategory: null,
      raw_count: 3,
      negated_count: 0,
      adjusted_count: 3,
      rate_per_1000: 1.2,
      is_introduced: false,
      is_removed: false,
      is_retained: true,
    };
    expect(passageLanguageSignalRowSchema.safeParse(row).success).toBe(true);
  });

  it("tolerates null optional count/rate/flag fields (upstream nulls)", () => {
    const row = {
      report_side: "LATER",
      category: "risk",
      subcategory: "climate_environmental",
      raw_count: 1,
      negated_count: null,
      adjusted_count: null,
      rate_per_1000: null,
      is_introduced: null,
      is_removed: null,
      is_retained: null,
    };
    expect(passageLanguageSignalRowSchema.safeParse(row).success).toBe(true);
  });

  it("rejects an invalid report_side", () => {
    const row = {
      report_side: "SIDEWAYS",
      category: "risk",
      subcategory: null,
      raw_count: 1,
      negated_count: 0,
      adjusted_count: 1,
      rate_per_1000: 1,
      is_introduced: false,
      is_removed: false,
      is_retained: false,
    };
    expect(passageLanguageSignalRowSchema.safeParse(row).success).toBe(false);
  });
});
