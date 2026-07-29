import "server-only";
import { query } from "@/lib/db/pool";
import { MalformedRowError } from "@/lib/db/errors";
import type {
  FilterOption,
  PassageFilterOptions,
  PassageLanguageSignal,
  PassageSearchParams,
  PassageSearchResult,
} from "@/lib/domain/passage";
import { MAX_COUNTED_PASSAGE_RESULTS } from "@/lib/domain/passage";
import {
  ALIGNMENT_STATUSES,
  ALIGNMENT_STATUS_LABELS,
  CONFIDENCE_LABELS,
  CONFIDENCE_LEVELS,
  PASSAGE_SORT_SQL,
  PASSAGE_TYPES,
  PASSAGE_TYPE_LABELS,
} from "@/lib/config/passage-vocabulary";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import {
  passageComparisonDetailRowSchema,
  passageLanguageSignalRowSchema,
  passageSearchRowSchema,
} from "@/lib/schemas/passage";
import {
  PASSAGE_COMPARISON_DETAIL_JOIN_SQL,
  PASSAGE_COMPARISON_DETAIL_ROW_COLUMNS_SQL,
  mapPassageComparisonDetailRow,
} from "@/lib/repositories/passage-mapper";
import type { PassageRepository } from "@/lib/repositories/passage-repository";
import type { PassageComparisonDetail } from "@/lib/domain/passage";

const RAW_QUALITIES = ["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"] as const;

/**
 * Turns a validated query string into the text `websearch_to_tsquery`
 * receives. `exactPhrase` wraps the whole (quote-stripped) input in a
 * single quoted phrase -- `websearch_to_tsquery` already treats a quoted
 * substring as a phrase search, so no separate `phraseto_tsquery` code path
 * is needed. Never string-interpolated into SQL; always passed as a bind
 * parameter, and `websearch_to_tsquery` itself never throws on malformed
 * input (unlike `to_tsquery`), which is exactly why it was chosen.
 */
function buildWebSearchQueryText(rawQuery: string, exactPhrase: boolean): string {
  if (!exactPhrase) return rawQuery;
  const stripped = rawQuery.replace(/"/g, "");
  return `"${stripped}"`;
}

interface WhereClause {
  whereSql: string;
  values: unknown[];
  rankSelectSql: string;
  usesQuery: boolean;
}

/**
 * Builds the shared `WHERE` clause (and rank expression) for both
 * `searchPassages` and `countPassageSearchResults` -- the two queries must
 * never drift on filter semantics, so this is the single source of truth
 * for translating validated `PassageSearchParams` into parameterized SQL.
 * Every value is a bind parameter; no filter value is ever concatenated
 * into the SQL text.
 */
function buildWhereClause(params: PassageSearchParams): WhereClause {
  const conditions: string[] = [];
  const values: unknown[] = [];
  let rankSelectSql = "NULL::real";

  if (params.query) {
    values.push(buildWebSearchQueryText(params.query, params.exactPhrase));
    const idx = values.length;
    conditions.push(`p.search_vector @@ websearch_to_tsquery('english', $${idx})`);
    rankSelectSql = `ts_rank(p.search_vector, websearch_to_tsquery('english', $${idx}))`;
  }

  if (params.company) {
    values.push(params.company);
    conditions.push(`c.ticker = $${values.length}`);
  }

  if (params.periodStart) {
    values.push(params.periodStart);
    conditions.push(`p.report_period_end >= $${values.length}`);
  }

  if (params.periodEnd) {
    values.push(params.periodEnd);
    conditions.push(`p.report_period_end <= $${values.length}`);
  }

  if (params.comparisonId) {
    values.push(params.comparisonId);
    conditions.push(`pc.report_comparison_id = $${values.length}`);
  }

  if (params.reportSide === "EARLIER") {
    conditions.push(`pc.earlier_passage_id = p.id`);
  } else if (params.reportSide === "LATER") {
    conditions.push(`pc.later_passage_id = p.id`);
  }

  if (params.alignmentStatus) {
    values.push(params.alignmentStatus);
    conditions.push(`pc.alignment_status = $${values.length}`);
  }

  if (params.confidence) {
    values.push(params.confidence);
    conditions.push(`pc.confidence = $${values.length}`);
  }

  if (params.passageType) {
    values.push(params.passageType);
    conditions.push(`p.passage_type = $${values.length}`);
  }

  if (params.category) {
    values.push(params.category);
    const categoryIdx = values.length;
    let subcategoryCondition = "";
    if (params.subcategory) {
      values.push(params.subcategory);
      subcategoryCondition = ` AND s.subcategory = $${values.length}`;
    }
    conditions.push(
      `EXISTS (SELECT 1 FROM app.current_passage_language_signals s WHERE s.passage_comparison_id = pc.id AND s.category = $${categoryIdx}${subcategoryCondition} AND s.raw_count > 0)`,
    );
  }

  if (params.reportSideQuality) {
    values.push(params.reportSideQuality);
    conditions.push(`rc.report_side_quality = $${values.length}`);
  }

  if (params.alignmentChangeQuality) {
    values.push(params.alignmentChangeQuality);
    conditions.push(`rc.alignment_change_quality = $${values.length}`);
  }

  if (params.primaryNarrativeEligible !== null) {
    values.push(params.primaryNarrativeEligible);
    conditions.push(`p.primary_narrative_eligible = $${values.length}`);
  }

  if (params.featureEligible !== null) {
    values.push(params.featureEligible);
    conditions.push(`p.feature_eligible = $${values.length}`);
  }

  if (params.irregularGapComparison !== null) {
    values.push(params.irregularGapComparison);
    conditions.push(`rc.is_irregular_gap = $${values.length}`);
  }

  if (params.collisionFlag !== null) {
    values.push(params.collisionFlag);
    conditions.push(`pc.collision_flag = $${values.length}`);
  }

  if (params.splitMergeFlag !== null) {
    values.push(params.splitMergeFlag);
    conditions.push(`pc.split_merge_flag = $${values.length}`);
  }

  return {
    whereSql: conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "",
    values,
    rankSelectSql,
    usesQuery: params.query !== null,
  };
}

const SEARCH_RESULT_FROM_JOIN_SQL = `
  FROM app.current_passages p
  JOIN app.current_companies c ON c.id = p.company_id
  LEFT JOIN app.current_passage_comparisons pc ON pc.earlier_passage_id = p.id OR pc.later_passage_id = p.id
  LEFT JOIN app.current_report_comparisons rc ON rc.id = pc.report_comparison_id
`;

function mapFilterOptions(
  rows: Array<{ value: string; label: string | null; option_count: number }>,
  knownOrder: readonly string[],
  labelFor: (value: string) => string,
): FilterOption[] {
  const byValue = new Map(rows.map((row) => [row.value, row]));
  const ordered: FilterOption[] = [];
  for (const value of knownOrder) {
    const row = byValue.get(value);
    if (row) {
      ordered.push({ value, label: labelFor(value), count: row.option_count });
      byValue.delete(value);
    }
  }
  // Any real value not in the known-order list (a future upstream addition)
  // still appears, alphabetically, rather than being silently dropped.
  const remaining = Array.from(byValue.values()).sort((a, b) => a.value.localeCompare(b.value));
  for (const row of remaining) {
    ordered.push({ value: row.value, label: row.label ?? labelFor(row.value), count: row.option_count });
  }
  return ordered;
}

export class PostgresPassageRepository implements PassageRepository {
  async searchPassages(params: PassageSearchParams): Promise<PassageSearchResult[]> {
    const { whereSql, values, rankSelectSql } = buildWhereClause(params);
    const sortSql = PASSAGE_SORT_SQL[params.sort];
    const limitIdx = values.length + 1;
    const offsetIdx = values.length + 2;
    const offset = (params.page - 1) * params.pageSize;

    // Built via string concatenation (never a `${}` interpolation directly
    // inside a `query(\`...\`)` template literal) -- every dynamic piece
    // here is either an internally-built, already-parameterized SQL
    // fragment (`whereSql`, `SEARCH_RESULT_FROM_JOIN_SQL`) or a numeric
    // bind-parameter position, never caller-supplied text.
    const sql =
      "SELECT " +
      `p.id AS passage_id,
       pc.id AS passage_comparison_id,
       pc.report_comparison_id,
       p.company_id,
       c.ticker AS company_ticker,
       c.name AS company_name,
       p.report_id,
       p.report_period_end,
       CASE WHEN pc.id IS NULL THEN NULL WHEN pc.earlier_passage_id = p.id THEN 'EARLIER' ELSE 'LATER' END AS report_side,
       rc.earlier_period_end,
       rc.later_period_end,
       p.heading,
       p.passage_type,
       p.structured_content_category,
       p.first_page_number,
       p.last_page_number,
       p.word_count,
       p.primary_narrative_eligible,
       p.feature_eligible,
       p.text,
       pc.alignment_status,
       pc.alignment_type,
       pc.confidence,
       pc.confidence_label,
       pc.collision_flag,
       pc.split_merge_flag,
       ` +
      rankSelectSql +
      " AS rank " +
      SEARCH_RESULT_FROM_JOIN_SQL +
      " " +
      whereSql +
      " ORDER BY " +
      sortSql +
      " LIMIT $" +
      limitIdx +
      " OFFSET $" +
      offsetIdx;

    const rows = await query(sql, [...values, params.pageSize, offset]);

    return rows.map((row, index) => {
      const parsed = passageSearchRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`passage-search-result[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      return {
        passageId: data.passage_id,
        passageComparisonId: data.passage_comparison_id,
        reportComparisonId: data.report_comparison_id,
        companyId: data.company_id,
        companyTicker: data.company_ticker,
        companyName: data.company_name,
        reportId: data.report_id,
        reportPeriodEnd: data.report_period_end,
        reportSide: data.report_side,
        earlierPeriodEnd: data.earlier_period_end,
        laterPeriodEnd: data.later_period_end,
        heading: data.heading,
        headingHighlight: null,
        passageType: data.passage_type,
        structuredContentCategory: data.structured_content_category as PassageSearchResult["structuredContentCategory"],
        firstPageNumber: data.first_page_number,
        lastPageNumber: data.last_page_number,
        wordCount: data.word_count,
        primaryNarrativeEligible: data.primary_narrative_eligible,
        featureEligible: data.feature_eligible,
        excerpt: [{ text: data.text, matched: false }],
        alignmentStatus: data.alignment_status,
        alignmentType: data.alignment_type,
        confidence: data.confidence,
        confidenceLabel: data.confidence_label,
        collisionFlag: data.collision_flag,
        splitMergeFlag: data.split_merge_flag,
        rank: data.rank,
      } satisfies PassageSearchResult;
    });
  }

  async countPassageSearchResults(params: PassageSearchParams): Promise<{ count: number; capped: boolean }> {
    const { whereSql, values } = buildWhereClause(params);
    const capIdx = values.length + 1;

    const countSql =
      "SELECT COUNT(*)::int AS counted FROM (SELECT 1 " +
      SEARCH_RESULT_FROM_JOIN_SQL +
      " " +
      whereSql +
      " LIMIT $" +
      capIdx +
      ") capped";

    const rows = await query<{ counted: number }>(countSql, [...values, MAX_COUNTED_PASSAGE_RESULTS + 1]);

    const counted = rows[0]?.counted ?? 0;
    const capped = counted > MAX_COUNTED_PASSAGE_RESULTS;
    return { count: capped ? MAX_COUNTED_PASSAGE_RESULTS : counted, capped };
  }

  async getPassageFilterOptions(): Promise<PassageFilterOptions> {
    const [companies, statuses, confidences, passageTypes, categories, qualities] = await Promise.all([
      query<{ ticker: string; name: string; display_order: number }>(
        `SELECT ticker, name, display_order FROM app.current_companies ORDER BY display_order`,
      ),
      query<{ value: string; label: string | null; option_count: number }>(
        `SELECT alignment_status AS value, NULL AS label, COUNT(*)::int AS option_count
         FROM app.current_passage_comparisons GROUP BY alignment_status`,
      ),
      query<{ value: string; label: string | null; option_count: number }>(
        `SELECT confidence AS value, NULL AS label, COUNT(*)::int AS option_count
         FROM app.current_passage_comparisons GROUP BY confidence`,
      ),
      query<{ value: string; label: string | null; option_count: number }>(
        `SELECT passage_type AS value, NULL AS label, COUNT(*)::int AS option_count
         FROM app.current_passages GROUP BY passage_type`,
      ),
      query<{ category: string; subcategory: string | null; option_count: number }>(
        `SELECT category, subcategory, COUNT(*)::int AS option_count
         FROM app.current_passage_language_signals
         WHERE raw_count > 0
         GROUP BY category, subcategory`,
      ),
      query<{ dimension: string; value: string; option_count: number }>(
        `SELECT 'report_side' AS dimension, report_side_quality AS value, COUNT(*)::int AS option_count
           FROM app.current_report_comparisons WHERE report_side_quality IS NOT NULL GROUP BY report_side_quality
         UNION ALL
         SELECT 'alignment_change' AS dimension, alignment_change_quality AS value, COUNT(*)::int AS option_count
           FROM app.current_report_comparisons WHERE alignment_change_quality IS NOT NULL GROUP BY alignment_change_quality`,
      ),
    ]);

    const categoryTotals = new Map<string, number>();
    const subcategoriesByCategory: Record<string, FilterOption[]> = {};
    for (const row of categories) {
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
    for (const key of Object.keys(subcategoriesByCategory)) {
      subcategoriesByCategory[key].sort((a, b) => a.label.localeCompare(b.label));
    }

    const reportSideQualityRows = qualities.filter((row) => row.dimension === "report_side");
    const alignmentChangeQualityRows = qualities.filter((row) => row.dimension === "alignment_change");

    return {
      companies: companies.map((row) => ({ value: row.ticker, label: `${row.name} (${row.ticker})` })),
      alignmentStatuses: mapFilterOptions(statuses, ALIGNMENT_STATUSES, (v) => ALIGNMENT_STATUS_LABELS[v as keyof typeof ALIGNMENT_STATUS_LABELS] ?? v),
      confidenceLevels: mapFilterOptions(confidences, CONFIDENCE_LEVELS, (v) => CONFIDENCE_LABELS[v as keyof typeof CONFIDENCE_LABELS] ?? v),
      passageTypes: mapFilterOptions(passageTypes, PASSAGE_TYPES, (v) => PASSAGE_TYPE_LABELS[v as keyof typeof PASSAGE_TYPE_LABELS] ?? v),
      categories: Array.from(categoryTotals.entries())
        .map(([value, count]) => ({ value, label: formatCategoryLabel(value), count }))
        .sort((a, b) => a.label.localeCompare(b.label)),
      subcategoriesByCategory,
      reportSideQualities: mapFilterOptions(
        reportSideQualityRows.map((row) => ({ value: row.value, label: null, option_count: row.option_count })),
        RAW_QUALITIES,
        (v) => v,
      ),
      alignmentChangeQualities: mapFilterOptions(
        alignmentChangeQualityRows.map((row) => ({ value: row.value, label: null, option_count: row.option_count })),
        RAW_QUALITIES,
        (v) => v,
      ),
    } satisfies PassageFilterOptions;
  }

  async getPassageComparisonById(passageComparisonId: string): Promise<PassageComparisonDetail | null> {
    const sql =
      "SELECT " + PASSAGE_COMPARISON_DETAIL_ROW_COLUMNS_SQL + " " + PASSAGE_COMPARISON_DETAIL_JOIN_SQL + " WHERE pc.id = $1";
    const rows = await query(sql, [passageComparisonId]);
    if (rows.length === 0) return null;

    const parsed = passageComparisonDetailRowSchema.safeParse(rows[0]);
    if (!parsed.success) {
      throw new MalformedRowError("passage-comparison-detail", parsed.error.message);
    }
    return mapPassageComparisonDetailRow(parsed.data);
  }

  async getPassageLanguageSignals(passageComparisonId: string): Promise<PassageLanguageSignal[]> {
    const rows = await query(
      `SELECT report_side, category, subcategory, raw_count, negated_count, adjusted_count,
              rate_per_1000, is_introduced, is_removed, is_retained
       FROM app.current_passage_language_signals
       WHERE passage_comparison_id = $1
       ORDER BY report_side, category, subcategory NULLS FIRST`,
      [passageComparisonId],
    );

    return rows.map((row, index) => {
      const parsed = passageLanguageSignalRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`passage-language-signal[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      return {
        reportSide: data.report_side,
        category: data.category,
        subcategory: data.subcategory,
        rawCount: data.raw_count,
        negatedCount: data.negated_count,
        adjustedCount: data.adjusted_count,
        ratePer1000: data.rate_per_1000,
        isIntroduced: data.is_introduced,
        isRemoved: data.is_removed,
        isRetained: data.is_retained,
      } satisfies PassageLanguageSignal;
    });
  }
}
