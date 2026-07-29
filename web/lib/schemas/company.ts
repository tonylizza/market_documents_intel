import { z } from "zod";

const rawQuality = z.enum(["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"]).nullable();

export const companyRowSchema = z.object({
  id: z.string(),
  ticker: z.string(),
  name: z.string(),
  sector: z.string().nullable(),
  description: z.string().nullable(),
  first_report_period_end: z.string().nullable(),
  latest_report_period_end: z.string().nullable(),
  report_count: z.number().int(),
  comparison_count: z.number().int(),
  latest_comparison_id: z.string().nullable(),
  historical_peak_comparison_id: z.string().nullable(),
  display_order: z.number().int(),
  has_current_data: z.boolean(),
});

export type CompanyRow = z.infer<typeof companyRowSchema>;

/**
 * Row shape for the single joined `app.current_companies` +
 * `app.current_report_comparisons` (latest-per-company) query behind
 * `getCompanyCardSummaries()`. Comparison columns are all nullable: a
 * company with only one report has no comparison yet, and the join is a
 * LEFT JOIN so that company still appears on the home page.
 */
export const companyCardRowSchema = z.object({
  company_id: z.string(),
  ticker: z.string(),
  name: z.string(),
  sector: z.string().nullable(),
  first_report_period_end: z.string().nullable(),
  latest_report_period_end: z.string().nullable(),
  report_count: z.number().int(),
  comparison_count: z.number().int(),
  historical_peak_comparison_id: z.string().nullable(),

  comparison_id: z.string().nullable(),
  earlier_period_end: z.string().nullable(),
  later_period_end: z.string().nullable(),
  gap_months: z.number().int().nullable(),
  is_transition: z.boolean().nullable(),
  is_irregular_gap: z.boolean().nullable(),
  is_latest_for_company: z.boolean().nullable(),
  is_historical_peak_change: z.boolean().nullable(),

  disclosure_change_score: z.number().nullable(),
  disclosure_change_label: z.string().nullable(),
  disclosure_change_percentile: z.number().nullable(),
  disclosure_change_quality: rawQuality,
  disclosure_change_quality_label: z.string().nullable(),
  disclosure_change_primary_eligible: z.boolean().nullable(),
  disclosure_change_warning: z.string().nullable(),

  net_tone_change: z.number().nullable(),
  net_tone_change_label: z.string().nullable(),
  uncertainty_change: z.number().nullable(),
  uncertainty_change_label: z.string().nullable(),
  risk_introduction_rate: z.number().nullable(),
  risk_introduction_label: z.string().nullable(),
  risk_removal_rate: z.number().nullable(),
  risk_removal_label: z.string().nullable(),
  governance_change: z.number().nullable(),
  governance_change_label: z.string().nullable(),
  financial_condition_change: z.number().nullable(),
  financial_condition_change_label: z.string().nullable(),

  report_side_quality: rawQuality,
  report_side_quality_label: z.string().nullable(),
  report_side_primary_eligible: z.boolean().nullable(),
  alignment_change_quality: rawQuality,
  alignment_change_quality_label: z.string().nullable(),
  alignment_change_primary_eligible: z.boolean().nullable(),

  primary_finding_key: z.string().nullable(),
  secondary_finding_key: z.string().nullable(),
  tertiary_finding_key: z.string().nullable(),
});

export type CompanyCardRow = z.infer<typeof companyCardRowSchema>;

export const discoveryItemRowSchema = z.object({
  id: z.string(),
  company_id: z.string(),
  ticker: z.string(),
  name: z.string(),
  report_comparison_id: z.string(),
  discovery_type: z.string(),
  rank: z.number().int(),
  percentile: z.number().nullable(),
  supporting_value: z.number(),
  supporting_unit: z.string(),
  quality_label: z.string(),
});

export type DiscoveryItemRow = z.infer<typeof discoveryItemRowSchema>;

export const applicationDataSummaryRowSchema = z.object({
  company_count: z.number().int(),
  report_count: z.number().int(),
  comparison_count: z.number().int(),
  earliest_period_end: z.string().nullable(),
  latest_period_end: z.string().nullable(),
});

export type ApplicationDataSummaryRow = z.infer<typeof applicationDataSummaryRowSchema>;
