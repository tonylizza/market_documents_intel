import "server-only";
import { query } from "@/lib/db/pool";
import { queryVector } from "@/lib/db/vector-query";
import { MalformedRowError } from "@/lib/db/errors";
import type { PassageSearchParams } from "@/lib/domain/passage";
import type { LexicalCandidate, RetrievalContext, SemanticCandidate, VectorSearchMode } from "@/lib/domain/retrieval";
import {
  lexicalCandidateRowSchema,
  retrievalContextRowSchema,
  semanticCandidateRowSchema,
} from "@/lib/schemas/retrieval";
import type { SemanticRetrievalRepository } from "@/lib/repositories/semantic-retrieval-repository";

/** Corpus-size threshold for `"auto"` -> concrete mode resolution. Chosen
 * from the Milestone 7B.1 real-corpus benchmark (~22,169 vectors): exact
 * and HNSW were both sub-3ms and recall@10 = 1.0 at that scale, with HNSW
 * ~30% faster unfiltered -- HNSW is preferred once the corpus is large
 * enough that a full sequential scan is no longer trivially cheap. This is
 * a documented, measured rule, not an unexamined guess. */
const AUTO_MODE_VECTOR_COUNT_THRESHOLD = 5_000;

/** Milestone 7B.1a: heading-frequency cache TTL. Joining a corpus-wide
 * heading-frequency aggregate directly into the vector-ORDER-BY query was
 * measured to turn a ~60ms candidate query into 15-80s (the join defeats
 * the planner's ability to stop scanning early once the index has produced
 * enough ordered rows) -- confirmed via `EXPLAIN ANALYZE` against the real
 * corpus. Computing it as its own simple, fast (~85ms) aggregate query and
 * caching the result avoids both the join and repeated recomputation. The
 * cache is invalidated by wall-clock TTL, not publication events -- a
 * `market-documents publish promote` in production is an infrequent,
 * deliberate operation, and a few minutes of staleness only affects the
 * quality-adjustment heuristic, never correctness of results returned. */
const HEADING_FREQUENCY_CACHE_TTL_MS = 5 * 60 * 1000;

declare global {
  var __headingFrequencyCache: { map: Map<string, number>; fetchedAt: number } | undefined;
}

async function getHeadingFrequencies(): Promise<Map<string, number>> {
  const cached = globalThis.__headingFrequencyCache;
  if (cached && Date.now() - cached.fetchedAt < HEADING_FREQUENCY_CACHE_TTL_MS) {
    return cached.map;
  }
  const rows = await query<{ heading: string; freq: number }>(
    `SELECT heading, count(*)::int AS freq FROM app.current_passages WHERE heading IS NOT NULL GROUP BY heading`,
  );
  const map = new Map(rows.map((r) => [r.heading, r.freq]));
  globalThis.__headingFrequencyCache = { map, fetchedAt: Date.now() };
  return map;
}

/** Bounded to the given candidate ids (never the whole corpus) -- true if
 * *any* retrieval context for that passage carries a published
 * financial-language category. */
async function getPassageIdsWithLanguageSignal(passageIds: readonly string[]): Promise<Set<string>> {
  if (passageIds.length === 0) return new Set();
  const rows = await query<{ passage_id: string }>(
    `SELECT DISTINCT rc.passage_id
     FROM app.current_retrieval_contexts rc
     JOIN app.current_retrieval_context_language_categories cat ON cat.retrieval_context_id = rc.id
     WHERE rc.passage_id = ANY($1::uuid[])`,
    [passageIds as string[]],
  );
  return new Set(rows.map((r) => r.passage_id));
}

function vectorLiteral(vector: readonly number[]): string {
  return `[${vector.join(",")}]`;
}

interface FilterClause {
  conditions: string[];
  values: unknown[];
}

/**
 * Builds passage/context-level structured-filter conditions shared by both
 * `searchSemanticCandidates` (aliases `p`/`c`, contexts via `EXISTS`) and
 * `expandRetrievalContexts` (aliases `rc`/`p`/`c` directly, no `EXISTS`
 * needed since `rc` already carries every context-scoped column). Kept
 * deliberately separate from `postgres-passage-repository.ts`'s
 * `buildWhereClause` -- that function's lexical-search SQL shape must never
 * change (see milestone: "preserve existing lexical URLs"), and this
 * function's join shape is genuinely different (embeddings-first, not
 * passage-comparisons-first).
 */
function buildPassageLevelFilters(params: PassageSearchParams, startIndex: number): FilterClause {
  const conditions: string[] = [];
  const values: unknown[] = [];
  let idx = startIndex;

  if (params.company) {
    idx += 1;
    values.push(params.company);
    conditions.push(`c.ticker = $${idx}`);
  }
  if (params.periodStart) {
    idx += 1;
    values.push(params.periodStart);
    conditions.push(`p.report_period_end >= $${idx}`);
  }
  if (params.periodEnd) {
    idx += 1;
    values.push(params.periodEnd);
    conditions.push(`p.report_period_end <= $${idx}`);
  }
  if (params.passageType) {
    idx += 1;
    values.push(params.passageType);
    conditions.push(`p.passage_type = $${idx}`);
  }
  if (params.primaryNarrativeEligible !== null) {
    idx += 1;
    values.push(params.primaryNarrativeEligible);
    conditions.push(`p.primary_narrative_eligible = $${idx}`);
  }
  if (params.featureEligible !== null) {
    idx += 1;
    values.push(params.featureEligible);
    conditions.push(`p.feature_eligible = $${idx}`);
  }

  return { conditions, values };
}

/** Context-scoped filters, expressed as an `EXISTS (... app.current_retrieval_contexts rc ...)`
 * fragment against a passage candidate (`p.id`) -- used only by the
 * semantic-candidate query, where contexts aren't already joined. */
function buildContextExistsFilter(params: PassageSearchParams, startIndex: number): FilterClause {
  const conditions: string[] = [];
  const values: unknown[] = [];
  let idx = startIndex;

  const hasContextFilter =
    params.comparisonId !== null ||
    params.reportSide !== null ||
    params.alignmentStatus !== null ||
    params.confidence !== null ||
    params.category !== null ||
    params.reportSideQuality !== null ||
    params.alignmentChangeQuality !== null ||
    params.irregularGapComparison !== null ||
    params.collisionFlag !== null ||
    params.splitMergeFlag !== null;

  if (!hasContextFilter) {
    return { conditions, values };
  }

  const rcConditions: string[] = [];
  if (params.comparisonId) {
    idx += 1;
    values.push(params.comparisonId);
    rcConditions.push(`rc.report_comparison_id = $${idx}`);
  }
  if (params.reportSide) {
    idx += 1;
    values.push(params.reportSide);
    rcConditions.push(`rc.report_side = $${idx}`);
  }
  if (params.alignmentStatus) {
    idx += 1;
    values.push(params.alignmentStatus);
    rcConditions.push(`rc.alignment_status = $${idx}`);
  }
  if (params.confidence) {
    idx += 1;
    values.push(params.confidence);
    rcConditions.push(`rc.confidence = $${idx}`);
  }
  if (params.reportSideQuality) {
    idx += 1;
    values.push(params.reportSideQuality);
    rcConditions.push(`rc.report_side_quality = $${idx}`);
  }
  if (params.alignmentChangeQuality) {
    idx += 1;
    values.push(params.alignmentChangeQuality);
    rcConditions.push(`rc.alignment_change_quality = $${idx}`);
  }
  if (params.irregularGapComparison !== null) {
    idx += 1;
    values.push(params.irregularGapComparison);
    rcConditions.push(`rc.irregular_gap_flag = $${idx}`);
  }
  if (params.collisionFlag !== null) {
    idx += 1;
    values.push(params.collisionFlag);
    rcConditions.push(`rc.collision_flag = $${idx}`);
  }
  if (params.splitMergeFlag !== null) {
    idx += 1;
    values.push(params.splitMergeFlag);
    rcConditions.push(`rc.split_merge_flag = $${idx}`);
  }
  if (params.category) {
    idx += 1;
    values.push(params.category);
    const categoryIdx = idx;
    let categoryJoinCondition = `cat.category = $${categoryIdx}`;
    if (params.subcategory) {
      idx += 1;
      values.push(params.subcategory);
      categoryJoinCondition += ` AND (SELECT 1 FROM app.current_retrieval_context_risk_subcategories rs WHERE rs.retrieval_context_id = rc.id AND rs.subcategory = $${idx}) IS NOT NULL`;
    }
    rcConditions.push(
      `EXISTS (SELECT 1 FROM app.current_retrieval_context_language_categories cat WHERE cat.retrieval_context_id = rc.id AND ${categoryJoinCondition})`,
    );
  }

  const whereRc = rcConditions.length > 0 ? ` AND ${rcConditions.join(" AND ")}` : "";
  conditions.push(`EXISTS (SELECT 1 FROM app.current_retrieval_contexts rc WHERE rc.passage_id = p.id${whereRc})`);
  return { conditions, values };
}

export class PostgresSemanticRetrievalRepository implements SemanticRetrievalRepository {
  async resolveVectorSearchMode(configured: VectorSearchMode): Promise<"exact" | "hnsw"> {
    if (configured !== "auto") return configured;
    const rows = await query<{ vector_count: number }>(
      `SELECT count(*)::int AS vector_count FROM app.current_passage_embeddings`,
    );
    const vectorCount = rows[0]?.vector_count ?? 0;
    return vectorCount >= AUTO_MODE_VECTOR_COUNT_THRESHOLD ? "hnsw" : "exact";
  }

  async searchSemanticCandidates(
    vector: number[],
    params: PassageSearchParams,
    limit: number,
    mode: VectorSearchMode,
  ): Promise<SemanticCandidate[]> {
    const effectiveMode = mode === "auto" ? await this.resolveVectorSearchMode(mode) : mode;

    const passageFilters = buildPassageLevelFilters(params, 0);
    const contextFilters = buildContextExistsFilter(params, passageFilters.values.length);
    const allValues = [...passageFilters.values, ...contextFilters.values];
    const vectorIdx = allValues.length + 1;
    const limitIdx = allValues.length + 2;

    const conditions = [...passageFilters.conditions, ...contextFilters.conditions];
    const whereSql = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";

    // Milestone 7B.1a: intentionally *not* joining the heading-frequency
    // aggregate or the language-signal EXISTS check into this query --
    // `EXPLAIN ANALYZE` against the real corpus showed either one turns a
    // ~60ms indexed vector scan into 15-80s, because the join/correlated
    // subquery defeats the planner's ability to stop scanning once the
    // ORDER BY + LIMIT is satisfied. Both are fetched afterward, bounded to
    // just this candidate set (see `getHeadingFrequencies`/
    // `getPassageIdsWithLanguageSignal` below) -- one small cached
    // aggregate query plus one `passage_id = ANY($ids)` lookup, both
    // measured at well under 150ms even unbounded/uncached.
    const sql =
      `SELECT
         pe.passage_id AS passage_id,
         (1 - (pe.embedding <=> $${vectorIdx}::vector)) AS similarity,
         p.heading AS heading,
         p.text AS text,
         p.word_count AS word_count
       FROM app.current_passage_embeddings pe
       JOIN app.current_passages p ON p.id = pe.passage_id
       JOIN app.current_companies c ON c.id = p.company_id
       ${whereSql}
       ORDER BY pe.embedding <=> $${vectorIdx}::vector
       LIMIT $${limitIdx}`;

    const rows = await queryVector(sql, [...allValues, vectorLiteral(vector), limit], effectiveMode === "hnsw" ? "hnsw" : "exact");

    const parsedRows = rows.map((row, index) => {
      const parsed = semanticCandidateRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`semantic-candidate[${index}]`, parsed.error.message);
      }
      return parsed.data;
    });

    const [headingFrequencies, languageSignalPassageIds] = await Promise.all([
      getHeadingFrequencies(),
      getPassageIdsWithLanguageSignal(parsedRows.map((r) => r.passage_id)),
    ]);

    return parsedRows.map((data) => {
      return {
        passageId: data.passage_id,
        similarity: data.similarity,
        heading: data.heading,
        text: data.text,
        wordCount: data.word_count,
        hasLanguageSignal: languageSignalPassageIds.has(data.passage_id),
        headingFrequency: (data.heading && headingFrequencies.get(data.heading)) || 0,
      } satisfies SemanticCandidate;
    });
  }

  async searchLexicalCandidates(params: PassageSearchParams, limit: number): Promise<LexicalCandidate[]> {
    if (!params.query) return [];

    const values: unknown[] = [params.query];
    const conditions = [`p.search_vector @@ websearch_to_tsquery('english', $1)`];

    if (params.company) {
      values.push(params.company);
      conditions.push(`c.ticker = $${values.length}`);
    }
    if (params.comparisonId) {
      values.push(params.comparisonId);
      conditions.push(`pc.report_comparison_id = $${values.length}`);
    }

    const limitIdx = values.length + 1;
    const sql =
      `SELECT p.id AS passage_id, pc.id AS passage_comparison_id,
              ts_rank(p.search_vector, websearch_to_tsquery('english', $1)) AS rank
       FROM app.current_passages p
       JOIN app.current_companies c ON c.id = p.company_id
       LEFT JOIN app.current_passage_comparisons pc ON pc.earlier_passage_id = p.id OR pc.later_passage_id = p.id
       WHERE ${conditions.join(" AND ")}
       ORDER BY rank DESC, p.id ASC
       LIMIT $${limitIdx}`;

    const rows = await query(sql, [...values, limit]);
    return rows.map((row, index) => {
      const parsed = lexicalCandidateRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`lexical-candidate[${index}]`, parsed.error.message);
      }
      return {
        passageId: parsed.data.passage_id,
        passageComparisonId: parsed.data.passage_comparison_id,
        rank: index,
        rankPosition: index + 1,
      } satisfies LexicalCandidate;
    });
  }

  async expandRetrievalContexts(passageIds: readonly string[], params: PassageSearchParams): Promise<RetrievalContext[]> {
    if (passageIds.length === 0) return [];

    const values: unknown[] = [passageIds as string[]];
    const conditions = [`rc.passage_id = ANY($1::uuid[])`];

    if (params.comparisonId) {
      values.push(params.comparisonId);
      conditions.push(`rc.report_comparison_id = $${values.length}`);
    }
    if (params.reportSide) {
      values.push(params.reportSide);
      conditions.push(`rc.report_side = $${values.length}`);
    }
    if (params.alignmentStatus) {
      values.push(params.alignmentStatus);
      conditions.push(`rc.alignment_status = $${values.length}`);
    }
    if (params.confidence) {
      values.push(params.confidence);
      conditions.push(`rc.confidence = $${values.length}`);
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
    if (params.passageType) {
      values.push(params.passageType);
      conditions.push(`rc.passage_type = $${values.length}`);
    }
    if (params.primaryNarrativeEligible !== null) {
      values.push(params.primaryNarrativeEligible);
      conditions.push(`rc.primary_narrative_eligible = $${values.length}`);
    }
    if (params.featureEligible !== null) {
      values.push(params.featureEligible);
      conditions.push(`rc.feature_eligible = $${values.length}`);
    }
    if (params.reportSideQuality) {
      values.push(params.reportSideQuality);
      conditions.push(`rc.report_side_quality = $${values.length}`);
    }
    if (params.alignmentChangeQuality) {
      values.push(params.alignmentChangeQuality);
      conditions.push(`rc.alignment_change_quality = $${values.length}`);
    }
    if (params.irregularGapComparison !== null) {
      values.push(params.irregularGapComparison);
      conditions.push(`rc.irregular_gap_flag = $${values.length}`);
    }
    if (params.collisionFlag !== null) {
      values.push(params.collisionFlag);
      conditions.push(`rc.collision_flag = $${values.length}`);
    }
    if (params.splitMergeFlag !== null) {
      values.push(params.splitMergeFlag);
      conditions.push(`rc.split_merge_flag = $${values.length}`);
    }
    if (params.category) {
      values.push(params.category);
      const categoryIdx = values.length;
      let categoryCondition = `cat.category = $${categoryIdx}`;
      if (params.subcategory) {
        values.push(params.subcategory);
        categoryCondition += ` AND EXISTS (SELECT 1 FROM app.current_retrieval_context_risk_subcategories rs2 WHERE rs2.retrieval_context_id = rc.id AND rs2.subcategory = $${values.length})`;
      }
      conditions.push(
        `EXISTS (SELECT 1 FROM app.current_retrieval_context_language_categories cat WHERE cat.retrieval_context_id = rc.id AND ${categoryCondition})`,
      );
    }

    const sql = `
      SELECT
        rc.id AS context_id,
        rc.passage_id,
        rc.context_type,
        rc.passage_comparison_id,
        rc.report_comparison_id,
        rc.report_id,
        rc.company_id,
        c.ticker AS company_ticker,
        c.name AS company_name,
        rc.report_side,
        rc.alignment_status,
        rc.alignment_type,
        rc.confidence,
        rc.report_period_end,
        rc.earlier_period_end,
        rc.later_period_end,
        rc.heading,
        rc.passage_type,
        rc.structured_content_category,
        rc.primary_narrative_eligible,
        rc.feature_eligible,
        rc.report_side_quality,
        rc.alignment_change_quality,
        rc.collision_flag,
        rc.split_merge_flag,
        rc.irregular_gap_flag,
        p.first_page_number,
        p.last_page_number,
        p.word_count,
        p.text,
        COALESCE(cat_agg.categories, ARRAY[]::text[]) AS categories,
        COALESCE(risk_agg.subcategories, ARRAY[]::text[]) AS risk_subcategories
      FROM app.current_retrieval_contexts rc
      JOIN app.current_passages p ON p.id = rc.passage_id
      JOIN app.current_companies c ON c.id = rc.company_id
      LEFT JOIN LATERAL (
        SELECT array_agg(category ORDER BY category) AS categories
        FROM app.current_retrieval_context_language_categories
        WHERE retrieval_context_id = rc.id
      ) cat_agg ON true
      LEFT JOIN LATERAL (
        SELECT array_agg(subcategory ORDER BY subcategory) AS subcategories
        FROM app.current_retrieval_context_risk_subcategories
        WHERE retrieval_context_id = rc.id
      ) risk_agg ON true
      WHERE ${conditions.join(" AND ")}
      ORDER BY rc.passage_id, rc.report_side NULLS FIRST
    `;

    const rows = await query(sql, values);
    return rows.map((row, index) => {
      const parsed = retrievalContextRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`retrieval-context[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      return {
        contextId: data.context_id,
        passageId: data.passage_id,
        contextType: data.context_type,
        passageComparisonId: data.passage_comparison_id,
        reportComparisonId: data.report_comparison_id,
        reportId: data.report_id,
        companyId: data.company_id,
        companyTicker: data.company_ticker,
        companyName: data.company_name,
        reportSide: data.report_side,
        alignmentStatus: data.alignment_status,
        alignmentType: data.alignment_type,
        confidence: data.confidence,
        reportPeriodEnd: data.report_period_end,
        earlierPeriodEnd: data.earlier_period_end,
        laterPeriodEnd: data.later_period_end,
        heading: data.heading,
        passageType: data.passage_type,
        structuredContentCategory: data.structured_content_category as RetrievalContext["structuredContentCategory"],
        primaryNarrativeEligible: data.primary_narrative_eligible,
        featureEligible: data.feature_eligible,
        reportSideQuality: data.report_side_quality,
        alignmentChangeQuality: data.alignment_change_quality,
        collisionFlag: data.collision_flag,
        splitMergeFlag: data.split_merge_flag,
        irregularGapFlag: data.irregular_gap_flag,
        firstPageNumber: data.first_page_number,
        lastPageNumber: data.last_page_number,
        wordCount: data.word_count,
        text: data.text,
        categories: data.categories,
        riskSubcategories: data.risk_subcategories,
      } satisfies RetrievalContext;
    });
  }
}
