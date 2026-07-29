import { z } from "zod";

const alignmentStatusSchema = z.enum([
  "NEW",
  "REMOVED",
  "UNCHANGED",
  "LIGHTLY_MODIFIED",
  "SUBSTANTIALLY_MODIFIED",
  "AMBIGUOUS",
]);

const alignmentTypeSchema = z.enum(["ONE_TO_ONE", "UNMATCHED_LATER", "UNMATCHED_EARLIER"]);

const confidenceSchema = z.enum(["HIGH", "MEDIUM", "LOW", "NEEDS_REVIEW"]);

const passageTypeSchema = z.enum(["HEADING_WITH_BODY", "MULTI_PARAGRAPH", "PARAGRAPH", "LIST", "TABLE_CONTEXT"]);

const reportSideSchema = z.enum(["EARLIER", "LATER"]);

/**
 * One `/passages` search-result row: `app.current_passages` LEFT JOINed to
 * at most one `app.current_passage_comparisons` row (see
 * `postgres-passage-repository.ts` for why a passage can legitimately
 * produce zero, one, or two result rows). Every alignment-scoped field is
 * nullable -- a report-only passage (no published alignment) is valid, not
 * malformed.
 */
export const passageSearchRowSchema = z.object({
  passage_id: z.string(),
  passage_comparison_id: z.string().nullable(),
  report_comparison_id: z.string().nullable(),
  company_id: z.string(),
  company_ticker: z.string(),
  company_name: z.string(),
  report_id: z.string(),
  report_period_end: z.string().nullable(),
  report_side: reportSideSchema.nullable(),
  earlier_period_end: z.string().nullable(),
  later_period_end: z.string().nullable(),
  heading: z.string().nullable(),
  passage_type: passageTypeSchema,
  structured_content_category: z.string().nullable(),
  first_page_number: z.number().int(),
  last_page_number: z.number().int(),
  word_count: z.number().int(),
  primary_narrative_eligible: z.boolean(),
  feature_eligible: z.boolean(),
  text: z.string(),
  alignment_status: alignmentStatusSchema.nullable(),
  alignment_type: alignmentTypeSchema.nullable(),
  confidence: confidenceSchema.nullable(),
  confidence_label: z.string().nullable(),
  collision_flag: z.boolean().nullable(),
  split_merge_flag: z.boolean().nullable(),
  rank: z.number().nullable(),
});

export type PassageSearchRow = z.infer<typeof passageSearchRowSchema>;

export const passageFilterOptionRowSchema = z.object({
  value: z.string(),
  label: z.string().nullable(),
  option_count: z.number().int(),
});

export type PassageFilterOptionRow = z.infer<typeof passageFilterOptionRowSchema>;

export const passageCategoryOptionRowSchema = z.object({
  category: z.string(),
  subcategory: z.string().nullable(),
  option_count: z.number().int(),
});

export type PassageCategoryOptionRow = z.infer<typeof passageCategoryOptionRowSchema>;

const rawQuality = z.enum(["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"]).nullable();

/**
 * Shared `app.current_passage_comparisons` (+ both joined
 * `app.current_passages` sides) row shape, used by both
 * `getPassageComparisonById` (single row) and `getComparisonEvidence` (one
 * row per evidence item) -- see `passage-mapper.ts`'s
 * `PASSAGE_COMPARISON_DETAIL_ROW_COLUMNS_SQL` for the exact shared SQL.
 */
export const passageComparisonDetailRowSchema = z.object({
  passage_comparison_id: z.string(),
  report_comparison_id: z.string(),
  company_id: z.string(),
  company_ticker: z.string(),
  company_name: z.string(),
  earlier_period_end: z.string().nullable(),
  later_period_end: z.string().nullable(),
  alignment_status: alignmentStatusSchema,
  alignment_type: alignmentTypeSchema,
  confidence: confidenceSchema,
  confidence_label: z.string(),
  content_score: z.number().nullable(),
  semantic_similarity: z.number().nullable(),
  lexical_similarity: z.number().nullable(),
  heading_similarity: z.number().nullable(),
  position_difference: z.number().nullable(),
  collision_flag: z.boolean(),
  split_merge_flag: z.boolean(),
  review_reason: z.string().nullable(),

  earlier_passage_id: z.string().nullable(),
  earlier_heading: z.string().nullable(),
  earlier_text: z.string().nullable(),
  earlier_word_count: z.number().int().nullable(),
  earlier_first_page_number: z.number().int().nullable(),
  earlier_last_page_number: z.number().int().nullable(),
  earlier_passage_type: passageTypeSchema.nullable(),
  earlier_structured_content_category: z.string().nullable(),
  earlier_primary_narrative_eligible: z.boolean().nullable(),
  earlier_feature_eligible: z.boolean().nullable(),

  later_passage_id: z.string().nullable(),
  later_heading: z.string().nullable(),
  later_text: z.string().nullable(),
  later_word_count: z.number().int().nullable(),
  later_first_page_number: z.number().int().nullable(),
  later_last_page_number: z.number().int().nullable(),
  later_passage_type: passageTypeSchema.nullable(),
  later_structured_content_category: z.string().nullable(),
  later_primary_narrative_eligible: z.boolean().nullable(),
  later_feature_eligible: z.boolean().nullable(),
});

export type PassageComparisonDetailRow = z.infer<typeof passageComparisonDetailRowSchema>;

export const comparisonEvidenceSummaryRowSchema = z.object({
  comparison_id: z.string(),
  company_id: z.string(),
  company_ticker: z.string(),
  company_name: z.string(),
  earlier_period_end: z.string().nullable(),
  later_period_end: z.string().nullable(),
  gap_months: z.number().int().nullable(),
  report_side_quality: rawQuality,
  report_side_quality_label: z.string().nullable(),
  alignment_change_quality: rawQuality,
  alignment_change_quality_label: z.string().nullable(),
});

export type ComparisonEvidenceSummaryRow = z.infer<typeof comparisonEvidenceSummaryRowSchema>;

export const passageStatusCountRowSchema = z.object({
  alignment_status: alignmentStatusSchema,
  bucket_count: z.number().int(),
});

export const passageLanguageSignalRowSchema = z.object({
  report_side: reportSideSchema,
  category: z.string(),
  subcategory: z.string().nullable(),
  raw_count: z.number().int(),
  negated_count: z.number().int().nullable(),
  adjusted_count: z.number().int().nullable(),
  rate_per_1000: z.number().nullable(),
  is_introduced: z.boolean().nullable(),
  is_removed: z.boolean().nullable(),
  is_retained: z.boolean().nullable(),
});

export type PassageLanguageSignalRow = z.infer<typeof passageLanguageSignalRowSchema>;
