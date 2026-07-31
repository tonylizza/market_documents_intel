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
const rawQualitySchema = z.enum(["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"]).nullable();
const contextTypeSchema = z.enum(["COMPARISON_LINKED", "REPORT_ONLY"]);

export const semanticCandidateRowSchema = z.object({
  passage_id: z.string(),
  similarity: z.number(),
  heading: z.string().nullable(),
  text: z.string(),
  word_count: z.number().int(),
});

export type SemanticCandidateRow = z.infer<typeof semanticCandidateRowSchema>;

export const lexicalCandidateRowSchema = z.object({
  passage_id: z.string(),
  passage_comparison_id: z.string().nullable(),
  rank: z.number().nullable(),
});

export type LexicalCandidateRow = z.infer<typeof lexicalCandidateRowSchema>;

/** One expanded `app.current_retrieval_contexts` row, joined with company
 * and passage-body fields -- the shared shape returned by
 * `expandRetrievalContexts` regardless of which mode requested expansion. */
export const retrievalContextRowSchema = z.object({
  context_id: z.string(),
  passage_id: z.string(),
  context_type: contextTypeSchema,
  passage_comparison_id: z.string().nullable(),
  report_comparison_id: z.string().nullable(),
  report_id: z.string(),
  company_id: z.string(),
  company_ticker: z.string(),
  company_name: z.string(),
  report_side: reportSideSchema.nullable(),
  alignment_status: alignmentStatusSchema.nullable(),
  alignment_type: alignmentTypeSchema.nullable(),
  confidence: confidenceSchema.nullable(),
  report_period_end: z.string().nullable(),
  earlier_period_end: z.string().nullable(),
  later_period_end: z.string().nullable(),
  heading: z.string().nullable(),
  passage_type: passageTypeSchema,
  structured_content_category: z.string().nullable(),
  primary_narrative_eligible: z.boolean(),
  feature_eligible: z.boolean(),
  report_side_quality: rawQualitySchema,
  alignment_change_quality: rawQualitySchema,
  collision_flag: z.boolean(),
  split_merge_flag: z.boolean(),
  irregular_gap_flag: z.boolean(),
  first_page_number: z.number().int(),
  last_page_number: z.number().int(),
  word_count: z.number().int(),
  text: z.string(),
  categories: z.array(z.string()),
  risk_subcategories: z.array(z.string()),
});

export type RetrievalContextRow = z.infer<typeof retrievalContextRowSchema>;
