import { z } from "zod";

const rawQuality = z.enum(["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"]).nullable();

/**
 * Full `app.current_report_comparisons` row shape (aliased `id AS
 * comparison_id`), shared by the company-history query (array, one company)
 * and the comparison-by-id query (single row + company join). Deliberately
 * excludes `new_passage_count`/etc. summary columns -- passage composition
 * is read directly from `app.current_passage_comparisons.alignment_status`
 * instead (a real, queryable value including `UNCHANGED`), never from these
 * upstream-computed counts.
 */
export const comparisonRowSchema = z.object({
  comparison_id: z.string(),
  company_id: z.string(),
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
  report_side_warning: z.string().nullable(),
  alignment_change_quality: rawQuality,
  alignment_change_quality_label: z.string().nullable(),
  alignment_change_primary_eligible: z.boolean().nullable(),
  alignment_change_warning: z.string().nullable(),

  dictionary_match_rate_earlier: z.number().nullable(),
  dictionary_match_rate_later: z.number().nullable(),
  ambiguous_word_share: z.number().nullable(),
  collision_flagged_word_share: z.number().nullable(),
  unmatched_word_share: z.number().nullable(),
  structured_content_exclusion_share: z.number().nullable(),

  primary_finding_key: z.string().nullable(),
  secondary_finding_key: z.string().nullable(),
  tertiary_finding_key: z.string().nullable(),
  finding_payload: z.record(z.string(), z.unknown()).nullable(),
});

export type ComparisonRow = z.infer<typeof comparisonRowSchema>;

export const comparisonDetailRowSchema = comparisonRowSchema.extend({
  company_ticker: z.string(),
  company_name: z.string(),
});

export type ComparisonDetailRow = z.infer<typeof comparisonDetailRowSchema>;

export const companyDetailRowSchema = z.object({
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
  latest_report_side_quality: rawQuality,
  latest_report_side_quality_label: z.string().nullable(),
});

export type CompanyDetailRow = z.infer<typeof companyDetailRowSchema>;

/** One `finding_payload[key]` entry -- validated on extraction, never the
 * raw JSONB blob passed into UI rendering. */
export const findingPayloadEntrySchema = z.object({
  value: z.number(),
  magnitude: z.number(),
});

export type FindingPayloadEntry = z.infer<typeof findingPayloadEntrySchema>;

/** Safely extracts and validates one candidate's entry from a comparison's
 * `finding_payload` -- returns `null` for a missing/malformed key rather
 * than throwing, since a payload legitimately contains only the candidates
 * that were eligible for *that* comparison. */
export function extractFindingPayloadEntry(
  payload: Record<string, unknown> | null,
  key: string,
): FindingPayloadEntry | null {
  if (!payload) return null;
  const parsed = findingPayloadEntrySchema.safeParse(payload[key]);
  return parsed.success ? parsed.data : null;
}

export const languageMetricRowSchema = z.object({
  id: z.string(),
  metric_scope: z.enum(["report_side", "alignment_change"]),
  population: z.string(),
  category: z.string(),
  subcategory: z.string().nullable(),
  earlier_rate_per_1000: z.number().nullable(),
  later_rate_per_1000: z.number().nullable(),
  rate_change: z.number().nullable(),
  absolute_rate_change: z.number().nullable(),
  introduced_rate_per_1000: z.number().nullable(),
  removed_rate_per_1000: z.number().nullable(),
  retained_count: z.number().int().nullable(),
  quality: rawQuality,
  primary_eligible: z.boolean().nullable(),
});

export type LanguageMetricRow = z.infer<typeof languageMetricRowSchema>;

export const passageCompositionRowSchema = z.object({
  alignment_status: z.enum(["NEW", "REMOVED", "SUBSTANTIALLY_MODIFIED", "LIGHTLY_MODIFIED", "UNCHANGED", "AMBIGUOUS"]),
  bucket_count: z.number().int(),
});

export type PassageCompositionRow = z.infer<typeof passageCompositionRowSchema>;
