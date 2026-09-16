import { z } from "zod";

/**
 * Track 7A.3/7A.4: row schemas + shared column-list SQL for
 * `app.current_narrative_unit_comparisons` /
 * `app.current_structured_table_comparisons`, mirroring
 * `schemas/comparison.ts` + `repositories/comparison-mapper.ts`'s own
 * shared-column-list/row-mapper convention.
 */

const comparisonResponseStatus = z.enum([
  "RESOLVED",
  "UNRESOLVED_UPSTREAM",
  "AMBIGUOUS",
  "REVIEW_REQUIRED",
  "NOT_AVAILABLE",
]);

const provenanceRefSchema = z
  .object({
    report_id: z.string(),
    directory_year: z.number().int(),
    start_page: z.number().int(),
    end_page: z.number().int().nullable(),
    source_block_ids: z.array(z.string()),
    source_excerpt: z.string().nullable(),
  })
  .nullable();

const lexicalMetricsSchema = z
  .object({
    tfidf_cosine: z.number().nullable(),
    unigram_jaccard: z.number().nullable(),
    bigram_jaccard: z.number().nullable(),
    edit_similarity: z.number().nullable(),
    sequence_similarity: z.number().nullable(),
    word_count_change: z.number().int().nullable(),
    word_count_change_pct: z.number().nullable(),
  })
  .nullable();

export const narrativeUnitComparisonRowSchema = z.object({
  schedule: z.string(),
  unit_key: z.string(),
  comparison_backend: z.literal("SEMANTIC_UNIT"),
  status: comparisonResponseStatus,
  alignment_status: z.string().nullable(),
  alignment_confidence: z.string().nullable(),
  analytical_mode: z.string().nullable(),
  lexical_metrics: lexicalMetricsSchema,
  earlier_word_count: z.number().int().nullable(),
  later_word_count: z.number().int().nullable(),
  earlier_provenance: provenanceRefSchema,
  later_provenance: provenanceRefSchema,
  review_reason: z.string().nullable(),
});
export type NarrativeUnitComparisonRow = z.infer<typeof narrativeUnitComparisonRowSchema>;

export const NARRATIVE_UNIT_COMPARISON_ROW_COLUMNS_SQL = `
  schedule,
  unit_key,
  comparison_backend,
  status,
  alignment_status,
  alignment_confidence,
  analytical_mode,
  lexical_metrics,
  earlier_word_count,
  later_word_count,
  earlier_provenance,
  later_provenance,
  review_reason
`;

const structuredRowAlignmentSchema = z.object({
  earlier_row_identity: z.string().nullable(),
  later_row_identity: z.string().nullable(),
  status: z.string(),
  confidence: z.string(),
  evidence: z.string(),
});

const structuredColumnAlignmentSchema = z.object({
  normalized_key: z.string().nullable(),
  is_restated: z.boolean(),
  status: z.string(),
  comparability_status: z.string(),
});

const structuredValueChangeEventSchema = z.object({
  row_identity: z.string().nullable(),
  column_normalized_key: z.string().nullable(),
  event_type: z.string(),
  earlier_raw_value: z.string().nullable(),
  later_raw_value: z.string().nullable(),
  earlier_numeric: z.number().nullable(),
  later_numeric: z.number().nullable(),
  absolute_change: z.number().nullable(),
  pct_change: z.number().nullable(),
});

export const structuredTableComparisonRowSchema = z.object({
  table_family_key: z.string(),
  comparison_backend: z.literal("STRUCTURED_TABLE"),
  status: comparisonResponseStatus,
  row_alignments: z.array(structuredRowAlignmentSchema),
  column_alignments: z.array(structuredColumnAlignmentSchema),
  value_change_events: z.array(structuredValueChangeEventSchema),
  footnotes: z.array(z.string()),
  earlier_provenance: provenanceRefSchema,
  later_provenance: provenanceRefSchema,
  review_reason: z.string().nullable(),
});
export type StructuredTableComparisonRow = z.infer<typeof structuredTableComparisonRowSchema>;

export const STRUCTURED_TABLE_COMPARISON_ROW_COLUMNS_SQL = `
  table_family_key,
  comparison_backend,
  status,
  row_alignments,
  column_alignments,
  value_change_events,
  footnotes,
  earlier_provenance,
  later_provenance,
  review_reason
`;
