import type {
  AlignmentStatus,
  AlignmentType,
  Confidence,
  PassageSortKey,
  PassageType,
  ReportSide,
  StructuredContentCategory,
} from "@/lib/domain/passage";

/**
 * Controlled vocabularies for every enum-style column exposed on
 * `app.current_passages`/`app.current_passage_comparisons`. Mirrors
 * `lib/formatting/labels.ts`'s existing pattern: raw values are preserved
 * internally (used in SQL, URL params, `data-*` attributes) and only ever
 * displayed through one of these label maps -- a raw value such as
 * `SUBSTANTIALLY_MODIFIED` must never reach rendered text.
 */

export const ALIGNMENT_STATUSES: readonly AlignmentStatus[] = [
  "NEW",
  "REMOVED",
  "UNCHANGED",
  "LIGHTLY_MODIFIED",
  "SUBSTANTIALLY_MODIFIED",
  "AMBIGUOUS",
];

export const ALIGNMENT_STATUS_LABELS: Record<AlignmentStatus, string> = {
  NEW: "New",
  REMOVED: "Removed",
  UNCHANGED: "Unchanged",
  LIGHTLY_MODIFIED: "Lightly modified",
  SUBSTANTIALLY_MODIFIED: "Substantially modified",
  AMBIGUOUS: "Ambiguous",
};

export const ALIGNMENT_TYPES: readonly AlignmentType[] = ["ONE_TO_ONE", "UNMATCHED_LATER", "UNMATCHED_EARLIER"];

export const ALIGNMENT_TYPE_LABELS: Record<AlignmentType, string> = {
  ONE_TO_ONE: "Matched one-to-one",
  UNMATCHED_LATER: "Unmatched (later report only)",
  UNMATCHED_EARLIER: "Unmatched (earlier report only)",
};

export const CONFIDENCE_LEVELS: readonly Confidence[] = ["HIGH", "MEDIUM", "LOW", "NEEDS_REVIEW"];

export const CONFIDENCE_LABELS: Record<Confidence, string> = {
  HIGH: "High confidence",
  MEDIUM: "Medium confidence",
  LOW: "Low confidence",
  NEEDS_REVIEW: "Needs review",
};

export const PASSAGE_TYPES: readonly PassageType[] = [
  "HEADING_WITH_BODY",
  "MULTI_PARAGRAPH",
  "PARAGRAPH",
  "LIST",
  "TABLE_CONTEXT",
];

export const PASSAGE_TYPE_LABELS: Record<PassageType, string> = {
  HEADING_WITH_BODY: "Heading with body",
  MULTI_PARAGRAPH: "Multi-paragraph",
  PARAGRAPH: "Paragraph",
  LIST: "List",
  TABLE_CONTEXT: "Table context",
};

export const REPORT_SIDES: readonly ReportSide[] = ["EARLIER", "LATER"];

export const REPORT_SIDE_LABELS: Record<ReportSide, string> = {
  EARLIER: "Earlier report",
  LATER: "Later report",
};

export const STRUCTURED_CONTENT_CATEGORY_LABELS: Record<StructuredContentCategory, string> = {
  list_content: "List content",
  numeric_or_table_like_source: "Numeric or table-like source",
  contents_or_index_like: "Contents or index-like",
  financial_table_rendered_as_prose: "Financial table rendered as prose",
  ordinary_prose_false_positive: "Ordinary prose (false positive)",
  legitimate_short_abbreviation: "Legitimate short abbreviation",
  caption_or_label_like: "Caption or label-like",
  table_context: "Table context",
  currency_exposure_table_mixed: "Currency exposure table (mixed)",
};

export function formatAlignmentStatusLabel(status: AlignmentStatus): string {
  return ALIGNMENT_STATUS_LABELS[status];
}

export function formatAlignmentTypeLabel(type: AlignmentType): string {
  return ALIGNMENT_TYPE_LABELS[type];
}

export function formatConfidenceLabel(confidence: Confidence): string {
  return CONFIDENCE_LABELS[confidence];
}

export function formatPassageTypeLabel(type: PassageType): string {
  return PASSAGE_TYPE_LABELS[type];
}

export function formatReportSideLabel(side: ReportSide): string {
  return REPORT_SIDE_LABELS[side];
}

export function formatStructuredContentCategoryLabel(category: string): string | null {
  return (STRUCTURED_CONTENT_CATEGORY_LABELS as Record<string, string>)[category] ?? null;
}

/**
 * Bounded sort-key -> SQL `ORDER BY` mapping. Every entry ends with a
 * deterministic tie-break (company, report period, passage index, passage
 * id) per the milestone brief -- never a bare, ties-possible `ORDER BY`.
 * `relevance` is only meaningful with a lexical query; the service layer
 * falls back to `newest_report` when `relevance` is requested without one.
 */
export const PASSAGE_SORT_SQL: Record<PassageSortKey, string> = {
  relevance: "rank DESC, c.ticker ASC, p.report_period_end DESC, p.passage_index ASC, p.id ASC",
  newest_report: "p.report_period_end DESC NULLS LAST, c.ticker ASC, p.passage_index ASC, p.id ASC",
  oldest_report: "p.report_period_end ASC NULLS LAST, c.ticker ASC, p.passage_index ASC, p.id ASC",
  company: "c.ticker ASC, p.report_period_end DESC NULLS LAST, p.passage_index ASC, p.id ASC",
  page_order: "c.ticker ASC, p.report_period_end DESC NULLS LAST, p.first_page_number ASC, p.passage_index ASC, p.id ASC",
};

export const PASSAGE_SORT_LABELS: Record<PassageSortKey, string> = {
  relevance: "Relevance",
  newest_report: "Newest report",
  oldest_report: "Oldest report",
  company: "Company",
  page_order: "Page order",
};
