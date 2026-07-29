import type { PassageComparisonDetailRow } from "@/lib/schemas/passage";
import type { PassageComparisonDetail, PassageSideDetail, StructuredContentCategory } from "@/lib/domain/passage";

/**
 * Shared column list for one `app.current_passage_comparisons` row LEFT
 * JOINed to both of its possible `app.current_passages` sides -- used
 * verbatim by both `getPassageComparisonById` (single row, `/passages/[id]`)
 * and `getComparisonEvidence` (many rows, `/comparisons/[id]/evidence`), so
 * the two routes can never drift on which fields are available. Aliased
 * `pc`/`ep`/`lp`/`rc`/`c` to match each repository's own join order.
 */
export const PASSAGE_COMPARISON_DETAIL_ROW_COLUMNS_SQL = `
  pc.id AS passage_comparison_id,
  pc.report_comparison_id,
  rc.company_id,
  c.ticker AS company_ticker,
  c.name AS company_name,
  rc.earlier_period_end,
  rc.later_period_end,
  pc.alignment_status,
  pc.alignment_type,
  pc.confidence,
  pc.confidence_label,
  pc.content_score,
  pc.semantic_similarity,
  pc.lexical_similarity,
  pc.heading_similarity,
  pc.position_difference,
  pc.collision_flag,
  pc.split_merge_flag,
  pc.review_reason,
  ep.id AS earlier_passage_id,
  ep.heading AS earlier_heading,
  ep.text AS earlier_text,
  ep.word_count AS earlier_word_count,
  ep.first_page_number AS earlier_first_page_number,
  ep.last_page_number AS earlier_last_page_number,
  ep.passage_type AS earlier_passage_type,
  ep.structured_content_category AS earlier_structured_content_category,
  ep.primary_narrative_eligible AS earlier_primary_narrative_eligible,
  ep.feature_eligible AS earlier_feature_eligible,
  lp.id AS later_passage_id,
  lp.heading AS later_heading,
  lp.text AS later_text,
  lp.word_count AS later_word_count,
  lp.first_page_number AS later_first_page_number,
  lp.last_page_number AS later_last_page_number,
  lp.passage_type AS later_passage_type,
  lp.structured_content_category AS later_structured_content_category,
  lp.primary_narrative_eligible AS later_primary_narrative_eligible,
  lp.feature_eligible AS later_feature_eligible
`;

export const PASSAGE_COMPARISON_DETAIL_JOIN_SQL = `
  FROM app.current_passage_comparisons pc
  JOIN app.current_report_comparisons rc ON rc.id = pc.report_comparison_id
  JOIN app.current_companies c ON c.id = rc.company_id
  LEFT JOIN app.current_passages ep ON ep.id = pc.earlier_passage_id
  LEFT JOIN app.current_passages lp ON lp.id = pc.later_passage_id
`;

function mapSide(
  row: PassageComparisonDetailRow,
  side: "earlier" | "later",
): PassageSideDetail | null {
  const id = side === "earlier" ? row.earlier_passage_id : row.later_passage_id;
  if (!id) return null;
  const prefix = side === "earlier" ? row.earlier_heading : row.later_heading;
  const text = side === "earlier" ? row.earlier_text : row.later_text;
  const wordCount = side === "earlier" ? row.earlier_word_count : row.later_word_count;
  const firstPage = side === "earlier" ? row.earlier_first_page_number : row.later_first_page_number;
  const lastPage = side === "earlier" ? row.earlier_last_page_number : row.later_last_page_number;
  const passageType = side === "earlier" ? row.earlier_passage_type : row.later_passage_type;
  const structuredCategory =
    side === "earlier" ? row.earlier_structured_content_category : row.later_structured_content_category;
  const primaryEligible =
    side === "earlier" ? row.earlier_primary_narrative_eligible : row.later_primary_narrative_eligible;
  const featureEligible = side === "earlier" ? row.earlier_feature_eligible : row.later_feature_eligible;

  return {
    passageId: id,
    heading: prefix,
    text: text ?? "",
    wordCount: wordCount ?? 0,
    firstPageNumber: firstPage ?? 0,
    lastPageNumber: lastPage ?? 0,
    passageType: passageType ?? "PARAGRAPH",
    structuredContentCategory: (structuredCategory as StructuredContentCategory | null) ?? null,
    primaryNarrativeEligible: primaryEligible ?? false,
    featureEligible: featureEligible ?? false,
  };
}

export function mapPassageComparisonDetailRow(row: PassageComparisonDetailRow): PassageComparisonDetail {
  return {
    passageComparisonId: row.passage_comparison_id,
    reportComparisonId: row.report_comparison_id,
    companyId: row.company_id,
    companyTicker: row.company_ticker,
    companyName: row.company_name,
    earlierPeriodEnd: row.earlier_period_end,
    laterPeriodEnd: row.later_period_end,
    alignmentStatus: row.alignment_status,
    alignmentType: row.alignment_type,
    confidence: row.confidence,
    confidenceLabel: row.confidence_label,
    contentScore: row.content_score,
    semanticSimilarity: row.semantic_similarity,
    lexicalSimilarity: row.lexical_similarity,
    headingSimilarity: row.heading_similarity,
    positionDifference: row.position_difference,
    collisionFlag: row.collision_flag,
    splitMergeFlag: row.split_merge_flag,
    reviewReason: row.review_reason,
    earlier: mapSide(row, "earlier"),
    later: mapSide(row, "later"),
  };
}
