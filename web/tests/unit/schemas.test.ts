import { describe, expect, it } from "vitest";
import { companyCardRowSchema, companyRowSchema } from "@/lib/schemas/company";
import { metricDefinitionRowSchema } from "@/lib/schemas/methodology";

const VALID_COMPANY_ROW = {
  id: "c1",
  ticker: "ACT",
  name: "Acme Corp",
  sector: null,
  description: null,
  first_report_period_end: "2016-06-30",
  latest_report_period_end: "2024-06-30",
  report_count: 9,
  comparison_count: 8,
  latest_comparison_id: "cmp-1",
  historical_peak_comparison_id: null,
  display_order: 0,
  has_current_data: true,
};

describe("companyRowSchema", () => {
  it("accepts a well-formed row", () => {
    expect(companyRowSchema.safeParse(VALID_COMPANY_ROW).success).toBe(true);
  });

  it("rejects a row missing a required field", () => {
    const withoutTicker: Record<string, unknown> = { ...VALID_COMPANY_ROW };
    delete withoutTicker.ticker;
    expect(companyRowSchema.safeParse(withoutTicker).success).toBe(false);
  });

  it("rejects a row with the wrong type for a numeric field", () => {
    expect(companyRowSchema.safeParse({ ...VALID_COMPANY_ROW, report_count: "nine" }).success).toBe(false);
  });

  it("rejects an unknown quality tier on the joined card row", () => {
    const row = {
      company_id: "c1",
      ticker: "ACT",
      name: "Acme Corp",
      sector: null,
      first_report_period_end: null,
      latest_report_period_end: null,
      report_count: 1,
      comparison_count: 0,
      historical_peak_comparison_id: null,
      comparison_id: null,
      earlier_period_end: null,
      later_period_end: null,
      gap_months: null,
      is_transition: null,
      is_irregular_gap: null,
      is_latest_for_company: null,
      is_historical_peak_change: null,
      disclosure_change_score: null,
      disclosure_change_label: null,
      disclosure_change_percentile: null,
      disclosure_change_quality: "NOT_A_REAL_TIER",
      disclosure_change_quality_label: null,
      disclosure_change_primary_eligible: null,
      disclosure_change_warning: null,
      net_tone_change: null,
      net_tone_change_label: null,
      uncertainty_change: null,
      uncertainty_change_label: null,
      risk_introduction_rate: null,
      risk_introduction_label: null,
      risk_removal_rate: null,
      risk_removal_label: null,
      governance_change: null,
      governance_change_label: null,
      financial_condition_change: null,
      financial_condition_change_label: null,
      report_side_quality: null,
      report_side_quality_label: null,
      report_side_primary_eligible: null,
      alignment_change_quality: null,
      alignment_change_quality_label: null,
      alignment_change_primary_eligible: null,
      primary_finding_key: null,
      secondary_finding_key: null,
      tertiary_finding_key: null,
    };
    expect(companyCardRowSchema.safeParse(row).success).toBe(false);
  });
});

describe("metricDefinitionRowSchema", () => {
  it("accepts a well-formed row", () => {
    const row = {
      metric_key: "disclosure_change_score",
      display_name: "Overall disclosure change",
      short_description: "short",
      technical_description: "technical",
      unit: "score_0_1",
      direction_interpretation: "higher is more change",
      methodology_anchor: "Milestone 3",
    };
    expect(metricDefinitionRowSchema.safeParse(row).success).toBe(true);
  });

  it("rejects a row missing a required text field", () => {
    const row = {
      metric_key: "disclosure_change_score",
      display_name: "Overall disclosure change",
      short_description: "short",
      unit: "score_0_1",
      direction_interpretation: "higher is more change",
      methodology_anchor: "Milestone 3",
    };
    expect(metricDefinitionRowSchema.safeParse(row).success).toBe(false);
  });
});
