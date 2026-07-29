import "server-only";
import { query } from "@/lib/db/pool";
import { MalformedRowError } from "@/lib/db/errors";
import type { LanguageMetric, PassageComposition, PassageCompositionStatus, ReportComparisonDetail } from "@/lib/domain/comparison";
import {
  comparisonDetailRowSchema,
  languageMetricRowSchema,
  passageCompositionRowSchema,
} from "@/lib/schemas/comparison";
import { COMPARISON_ROW_COLUMNS_SQL, mapComparisonRow } from "@/lib/repositories/comparison-mapper";
import type { ComparisonRepository } from "@/lib/repositories/comparison-repository";
import type {
  ComparisonEvidenceFilterOptions,
  ComparisonEvidenceFilters,
  ComparisonEvidenceItem,
  FilterOption,
} from "@/lib/domain/passage";
import { MAX_EXCERPT_LENGTH } from "@/lib/domain/passage";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import { formatConfidenceLabel } from "@/lib/config/passage-vocabulary";
import type { Confidence } from "@/lib/domain/passage";
import { passageComparisonDetailRowSchema } from "@/lib/schemas/passage";
import {
  PASSAGE_COMPARISON_DETAIL_JOIN_SQL,
  PASSAGE_COMPARISON_DETAIL_ROW_COLUMNS_SQL,
  mapPassageComparisonDetailRow,
} from "@/lib/repositories/passage-mapper";

function truncateExcerpt(text: string): string {
  if (text.length <= MAX_EXCERPT_LENGTH) return text;
  return `${text.slice(0, MAX_EXCERPT_LENGTH).trimEnd()}…`;
}

/**
 * Builds the shared filtered-evidence `WHERE` clause for both
 * `getComparisonEvidence` and `countComparisonEvidence` -- always anchored
 * to one `report_comparison_id`, so an evidence query can never leak rows
 * from another comparison regardless of which optional filters are set.
 */
function buildEvidenceWhereClause(comparisonId: string, filters: ComparisonEvidenceFilters): { whereSql: string; values: unknown[] } {
  const values: unknown[] = [comparisonId];
  const conditions = ["pc.report_comparison_id = $1"];

  if (filters.status !== "ALL") {
    values.push(filters.status);
    conditions.push(`pc.alignment_status = $${values.length}`);
  }
  if (filters.confidence) {
    values.push(filters.confidence);
    conditions.push(`pc.confidence = $${values.length}`);
  }
  if (filters.collisionFlag !== null) {
    values.push(filters.collisionFlag);
    conditions.push(`pc.collision_flag = $${values.length}`);
  }
  if (filters.splitMergeFlag !== null) {
    values.push(filters.splitMergeFlag);
    conditions.push(`pc.split_merge_flag = $${values.length}`);
  }
  if (filters.hasHeading !== null) {
    conditions.push(
      filters.hasHeading
        ? `(ep.heading IS NOT NULL OR lp.heading IS NOT NULL)`
        : `(ep.heading IS NULL AND lp.heading IS NULL)`,
    );
  }
  if (filters.pageStart !== null) {
    values.push(filters.pageStart);
    conditions.push(`COALESCE(ep.first_page_number, lp.first_page_number) >= $${values.length}`);
  }
  if (filters.pageEnd !== null) {
    values.push(filters.pageEnd);
    conditions.push(`COALESCE(ep.last_page_number, lp.last_page_number) <= $${values.length}`);
  }
  if (filters.category) {
    values.push(filters.category);
    const categoryIdx = values.length;
    let subcategorySql = "";
    if (filters.subcategory) {
      values.push(filters.subcategory);
      subcategorySql = ` AND s.subcategory = $${values.length}`;
    }
    conditions.push(
      `EXISTS (SELECT 1 FROM app.current_passage_language_signals s WHERE s.passage_comparison_id = pc.id AND s.category = $${categoryIdx}${subcategorySql} AND s.raw_count > 0)`,
    );
  }

  return { whereSql: `WHERE ${conditions.join(" AND ")}`, values };
}

const ALL_PASSAGE_STATUSES: readonly PassageCompositionStatus[] = [
  "NEW",
  "REMOVED",
  "SUBSTANTIALLY_MODIFIED",
  "LIGHTLY_MODIFIED",
  "UNCHANGED",
  "AMBIGUOUS",
];

const PASSAGE_COMPOSITION_QUALITY_NOTE =
  "Composition reflects passage-level alignment status. AMBIGUOUS passages have uncertain attribution and are not counted as NEW, REMOVED, or MODIFIED.";

export class PostgresComparisonRepository implements ComparisonRepository {
  async getComparisonById(comparisonId: string): Promise<ReportComparisonDetail | null> {
    const rows = await query(
      "SELECT " +
        COMPARISON_ROW_COLUMNS_SQL +
        `,
              c.ticker AS company_ticker,
              c.name AS company_name
       FROM app.current_report_comparisons rc
       JOIN app.current_companies c ON c.id = rc.company_id
       WHERE rc.id = $1`,
      [comparisonId],
    );
    if (rows.length === 0) return null;

    const parsed = comparisonDetailRowSchema.safeParse(rows[0]);
    if (!parsed.success) {
      throw new MalformedRowError("comparison-detail", parsed.error.message);
    }
    const data = parsed.data;
    return {
      ...mapComparisonRow(data),
      companyTicker: data.company_ticker,
      companyName: data.company_name,
      dictionaryMatchRateEarlier: data.dictionary_match_rate_earlier,
      dictionaryMatchRateLater: data.dictionary_match_rate_later,
      ambiguousWordShare: data.ambiguous_word_share,
      collisionFlaggedWordShare: data.collision_flagged_word_share,
      unmatchedWordShare: data.unmatched_word_share,
      structuredContentExclusionShare: data.structured_content_exclusion_share,
      reportSideWarning: data.report_side_warning,
      alignmentChangeWarning: data.alignment_change_warning,
    } satisfies ReportComparisonDetail;
  }

  async getComparisonLanguageMetrics(comparisonId: string): Promise<LanguageMetric[]> {
    const rows = await query(
      `SELECT id, metric_scope, population, category, subcategory,
              earlier_rate_per_1000, later_rate_per_1000, rate_change, absolute_rate_change,
              introduced_rate_per_1000, removed_rate_per_1000, retained_count, quality, primary_eligible
       FROM app.current_language_metrics
       WHERE report_comparison_id = $1
       ORDER BY metric_scope, population, category`,
      [comparisonId],
    );

    return rows.map((row, index) => {
      const parsed = languageMetricRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`app.current_language_metrics[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      return {
        id: data.id,
        scope: data.metric_scope,
        population: data.population,
        category: data.category,
        subcategory: data.subcategory,
        earlierRatePer1000: data.earlier_rate_per_1000,
        laterRatePer1000: data.later_rate_per_1000,
        rateChange: data.rate_change,
        absoluteRateChange: data.absolute_rate_change,
        introducedRatePer1000: data.introduced_rate_per_1000,
        removedRatePer1000: data.removed_rate_per_1000,
        retainedCount: data.retained_count,
        quality: data.quality,
        primaryEligible: data.primary_eligible,
      } satisfies LanguageMetric;
    });
  }

  async getComparisonPassageComposition(comparisonId: string): Promise<PassageComposition> {
    const rows = await query(
      `SELECT alignment_status, COUNT(*)::int AS bucket_count
       FROM app.current_passage_comparisons
       WHERE report_comparison_id = $1
       GROUP BY alignment_status`,
      [comparisonId],
    );

    const countByStatus = new Map<PassageCompositionStatus, number>();
    rows.forEach((row, index) => {
      const parsed = passageCompositionRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`passage-composition[${index}]`, parsed.error.message);
      }
      countByStatus.set(parsed.data.alignment_status, parsed.data.bucket_count);
    });

    const totalCount = Array.from(countByStatus.values()).reduce((sum, count) => sum + count, 0);
    const buckets = ALL_PASSAGE_STATUSES.map((status) => {
      const count = countByStatus.get(status) ?? 0;
      return { status, count, share: totalCount > 0 ? count / totalCount : 0 };
    });

    return {
      comparisonId,
      totalCount,
      buckets,
      qualityNote: PASSAGE_COMPOSITION_QUALITY_NOTE,
    } satisfies PassageComposition;
  }

  async getComparisonEvidence(comparisonId: string, filters: ComparisonEvidenceFilters): Promise<ComparisonEvidenceItem[]> {
    const { whereSql, values } = buildEvidenceWhereClause(comparisonId, filters);
    const limitIdx = values.length + 1;
    const offsetIdx = values.length + 2;
    const offset = (filters.page - 1) * filters.pageSize;

    const sql =
      "SELECT " +
      PASSAGE_COMPARISON_DETAIL_ROW_COLUMNS_SQL +
      " " +
      PASSAGE_COMPARISON_DETAIL_JOIN_SQL +
      " " +
      whereSql +
      " ORDER BY COALESCE(ep.first_page_number, lp.first_page_number) ASC NULLS LAST, pc.id ASC LIMIT $" +
      limitIdx +
      " OFFSET $" +
      offsetIdx;
    const rows = await query(sql, [...values, filters.pageSize, offset]);

    return rows.map((row, index) => {
      const parsed = passageComparisonDetailRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`comparison-evidence-item[${index}]`, parsed.error.message);
      }
      const detail = mapPassageComparisonDetailRow(parsed.data);
      return {
        passageComparisonId: detail.passageComparisonId,
        alignmentStatus: detail.alignmentStatus,
        alignmentType: detail.alignmentType,
        confidence: detail.confidence,
        confidenceLabel: detail.confidenceLabel,
        collisionFlag: detail.collisionFlag,
        splitMergeFlag: detail.splitMergeFlag,
        contentScore: detail.contentScore,
        earlier: detail.earlier
          ? {
              passageId: detail.earlier.passageId,
              heading: detail.earlier.heading,
              excerpt: [{ text: truncateExcerpt(detail.earlier.text), matched: false }],
              firstPageNumber: detail.earlier.firstPageNumber,
              lastPageNumber: detail.earlier.lastPageNumber,
              wordCount: detail.earlier.wordCount,
            }
          : null,
        later: detail.later
          ? {
              passageId: detail.later.passageId,
              heading: detail.later.heading,
              excerpt: [{ text: truncateExcerpt(detail.later.text), matched: false }],
              firstPageNumber: detail.later.firstPageNumber,
              lastPageNumber: detail.later.lastPageNumber,
              wordCount: detail.later.wordCount,
            }
          : null,
      } satisfies ComparisonEvidenceItem;
    });
  }

  async countComparisonEvidence(comparisonId: string, filters: ComparisonEvidenceFilters): Promise<number> {
    const { whereSql, values } = buildEvidenceWhereClause(comparisonId, filters);
    const sql = "SELECT COUNT(*)::int AS counted " + PASSAGE_COMPARISON_DETAIL_JOIN_SQL + " " + whereSql;
    const rows = await query<{ counted: number }>(sql, values);
    return rows[0]?.counted ?? 0;
  }

  async getComparisonEvidenceFilterOptions(comparisonId: string): Promise<ComparisonEvidenceFilterOptions> {
    const [confidenceRows, categoryRows] = await Promise.all([
      query<{ value: string; option_count: number }>(
        `SELECT confidence AS value, COUNT(*)::int AS option_count
         FROM app.current_passage_comparisons
         WHERE report_comparison_id = $1
         GROUP BY confidence`,
        [comparisonId],
      ),
      query<{ category: string; subcategory: string | null; option_count: number }>(
        `SELECT category, subcategory, COUNT(*)::int AS option_count
         FROM app.current_passage_language_signals
         WHERE report_comparison_id = $1 AND raw_count > 0
         GROUP BY category, subcategory`,
        [comparisonId],
      ),
    ]);

    const categoryTotals = new Map<string, number>();
    const subcategoriesByCategory: Record<string, FilterOption[]> = {};
    for (const row of categoryRows) {
      categoryTotals.set(row.category, (categoryTotals.get(row.category) ?? 0) + row.option_count);
      if (row.subcategory) {
        subcategoriesByCategory[row.category] ??= [];
        subcategoriesByCategory[row.category].push({
          value: row.subcategory,
          label: formatCategoryLabel(row.subcategory),
          count: row.option_count,
        });
      }
    }

    return {
      confidenceLevels: confidenceRows.map((row) => ({
        value: row.value,
        label: formatConfidenceLabel(row.value as Confidence),
        count: row.option_count,
      })),
      categories: Array.from(categoryTotals.entries())
        .map(([value, count]) => ({ value, label: formatCategoryLabel(value), count }))
        .sort((a, b) => a.label.localeCompare(b.label)),
      subcategoriesByCategory,
    } satisfies ComparisonEvidenceFilterOptions;
  }
}
