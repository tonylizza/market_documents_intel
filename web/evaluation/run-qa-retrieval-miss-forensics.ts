/**
 * Milestone 7B.1d Phase 1: retrieval-miss forensic analysis for the 13
 * `RETRIEVAL_MISS` cases identified by `run-qa-failure-attribution.ts`
 * (`web/evaluation/results/qa_failure_attribution.csv`, milestone 7B.1c
 * baseline). Diagnoses *why* each case's required evidence never enters the
 * merged candidate pool -- short/heading-only passage, missing embedding,
 * heading-dependent context, neighbor-dependent context, comparison-side
 * dependency, or genuinely under-ranked -- before any chunk-construction
 * code is written, per the milestone brief's explicit ordering requirement.
 *
 * Script (`tsx --tsconfig evaluation/tsconfig.json
 * evaluation/run-qa-retrieval-miss-forensics.ts`), not a unit test: requires
 * `APP_READONLY_DATABASE_URL` and `QUERY_EMBEDDING_SERVICE_URL`, same as
 * `run-qa-failure-attribution.ts`.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { PostgresSemanticRetrievalRepository } from "../lib/repositories/postgres-semantic-retrieval-repository";
import { PostgresCompanyRepository } from "../lib/repositories/postgres-company-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "../lib/services/query-embedding-provider";
import { analyzeQuestion } from "../lib/services/qa/query-analysis";
import { generateCandidates } from "../lib/services/qa/candidate-generation";
import { createQaReranker } from "../lib/services/qa/qa-reranker";
import { enrichWithDirectResponsiveness } from "../lib/services/qa/direct-responsiveness";
import { getQaConfig, getGateStrategyConfig } from "../lib/config/qa-config";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { query, closePool } from "../lib/db/pool";
import { QA_EVALUATION_DATASET } from "./qa-dataset";

/** The 13 `RETRIEVAL_MISS` case ids from the 7B.1c baseline run (verified
 * live against `web/evaluation/results/qa_failure_attribution.csv` before
 * writing this script). */
const RETRIEVAL_MISS_CASE_IDS = new Set([
  "sup-act-financial-growth",
  "sup-sdl-strategy-sovereign-risk",
  "sup-period-kp2-2024",
  "partial-act-diversity-and-gender-pay-gap",
  "numeric-trap-short-heading-operations",
  "short-heading-trap-usd-currency",
  "broad-corpus-governance-practices",
  "multi-company-remuneration-comparison",
  "quality-aware-act-remuneration-short",
  "direction-lexical-act-growth-increase",
  "direction-lexical-bel-repurchase-removed",
  "chronology-kp2-hse-governance-timeline",
  "partial-sur-target-setting-and-exact-budget",
]);

interface PassageRow {
  id: string;
  report_id: string;
  passage_index: number;
  heading: string | null;
  first_page_number: number;
  last_page_number: number;
  word_count: number;
  passage_type: string;
}

interface ComparisonRow {
  id: string;
  report_comparison_id: string;
  earlier_passage_id: string | null;
  later_passage_id: string | null;
  alignment_status: string;
}

interface ForensicRow {
  caseId: string;
  question: string;
  expectedPassageIds: string;
  expectedRetrievalContextCount: number;
  passageLength: number | "";
  heading: string;
  headingIsOwn: boolean;
  previousPassageId: string;
  nextPassageId: string;
  earlierComparisonPassageId: string;
  laterComparisonPassageId: string;
  comparisonAlignmentStatus: string;
  vectorAvailable: boolean;
  currentKeywordRank: number | "";
  currentSemanticRank: number | "";
  mergedCandidateStatus: "PRESENT" | "ABSENT";
  diagnosedDependency: string;
  recommendedRepresentation: string;
}

function csvEscape(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

/** Walk backward within the same report (by passage_index) to find the
 * nearest heading -- mirrors the research-layer segmentation rule where
 * `heading_text` is only stamped on the first passage of a heading-started
 * run (see `passage_segmentation.py::_pack_run_into_passages`). */
function resolveEffectiveHeading(reportPassages: PassageRow[], targetIndex: number): { heading: string | null; isOwn: boolean } {
  const target = reportPassages.find((p) => p.passage_index === targetIndex);
  if (target?.heading) return { heading: target.heading, isOwn: true };
  const sorted = [...reportPassages].sort((a, b) => a.passage_index - b.passage_index);
  const pos = sorted.findIndex((p) => p.passage_index === targetIndex);
  for (let i = pos - 1; i >= 0; i--) {
    if (sorted[i].heading) return { heading: sorted[i].heading, isOwn: false };
  }
  return { heading: null, isOwn: false };
}

function neighborId(reportPassages: PassageRow[], targetIndex: number, direction: 1 | -1): string {
  const sorted = [...reportPassages].sort((a, b) => a.passage_index - b.passage_index);
  const pos = sorted.findIndex((p) => p.passage_index === targetIndex);
  const neighbor = sorted[pos + direction];
  return neighbor ? neighbor.id : "";
}

function diagnose(
  passage: PassageRow | undefined,
  effectiveHeading: { heading: string | null; isOwn: boolean },
  comparisonRows: ComparisonRow[],
  vectorAvailable: boolean,
  mergedPresent: boolean,
  caseType: string,
): { dependency: string; recommendation: string } {
  if (!passage) {
    return { dependency: "PASSAGE_NOT_FOUND_IN_ACTIVE_PUBLICATION", recommendation: "GROUND_TRUTH_REPAIR" };
  }
  if (!vectorAvailable) {
    return { dependency: "MISSING_CANONICAL_EMBEDDING_512_TOKEN_EXCLUSION", recommendation: "HEADING_PLUS_PASSAGE" };
  }
  const isShort = passage.word_count < 20;
  const headingDependent = !effectiveHeading.isOwn && effectiveHeading.heading !== null;
  const hasComparisonLink = comparisonRows.length > 0;
  const requiresBothSides = caseType === "requires_chronology";
  const requiresComparisonDirection = caseType === "requires_comparison_direction";

  if (requiresBothSides || (requiresComparisonDirection && hasComparisonLink)) {
    return { dependency: "COMPARISON_BOTH_SIDES_JOINTLY_MEANINGFUL", recommendation: "COMPARISON_PAIR" };
  }
  if (isShort && headingDependent) {
    return { dependency: "SHORT_PASSAGE_DEPENDENT_ON_PRECEDING_HEADING", recommendation: "HEADING_PLUS_PASSAGE" };
  }
  if (isShort) {
    return { dependency: "SHORT_PASSAGE_DILUTED_OR_INSUFFICIENT_STANDALONE_SIGNAL", recommendation: "LOCAL_WINDOW" };
  }
  if (headingDependent) {
    return { dependency: "DEPENDENT_ON_PRECEDING_HEADING_NOT_ATTACHED_TO_PASSAGE", recommendation: "HEADING_PLUS_PASSAGE" };
  }
  if (caseType === "broad_corpus_wide" || caseType === "multi_company") {
    return { dependency: "SCOPE_ROUTING_NOT_A_CHUNK_SHAPE_PROBLEM", recommendation: "QUERY_TYPE_ROUTING_EXPERIMENT" };
  }
  if (mergedPresent) {
    return { dependency: "PRESENT_BUT_UNDER_RANKED", recommendation: "HEADING_PLUS_PASSAGE_OR_LOCAL_WINDOW" };
  }
  return { dependency: "LONG_OR_TOPICALLY_DILUTED_PASSAGE_NEVER_SURFACES", recommendation: "LOCAL_WINDOW" };
}

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const companyRepo = new PostgresCompanyRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);
  const config = getQaConfig();

  const companies = await companyRepo.listCompanies();
  const testCases = QA_EVALUATION_DATASET.filter((c) => RETRIEVAL_MISS_CASE_IDS.has(c.id));
  if (testCases.length !== RETRIEVAL_MISS_CASE_IDS.size) {
    throw new Error(
      `Expected ${RETRIEVAL_MISS_CASE_IDS.size} retrieval-miss cases in QA_EVALUATION_DATASET, found ${testCases.length} -- dataset drifted from the 7B.1c baseline this script was written against.`,
    );
  }

  const allExpectedPassageIds = Array.from(
    new Set(testCases.flatMap((c) => c.minimumSufficientEvidenceSets.flat())),
  );

  const passageRows = await query<PassageRow>(
    `SELECT id, report_id, passage_index, heading, first_page_number, last_page_number, word_count, passage_type
     FROM app.current_passages
     WHERE id = ANY($1::uuid[])`,
    [allExpectedPassageIds],
  );
  const passageById = new Map(passageRows.map((p) => [p.id, p]));

  const reportIds = Array.from(new Set(passageRows.map((p) => p.report_id)));
  const reportPassageRows = reportIds.length
    ? await query<PassageRow>(
        `SELECT id, report_id, passage_index, heading, first_page_number, last_page_number, word_count, passage_type
         FROM app.current_passages
         WHERE report_id = ANY($1::uuid[])
         ORDER BY report_id, passage_index`,
        [reportIds],
      )
    : [];
  const passagesByReport = new Map<string, PassageRow[]>();
  for (const p of reportPassageRows) {
    const arr = passagesByReport.get(p.report_id) ?? [];
    arr.push(p);
    passagesByReport.set(p.report_id, arr);
  }

  const embeddingRows = allExpectedPassageIds.length
    ? await query<{ passage_id: string }>(
        `SELECT passage_id FROM app.current_passage_embeddings WHERE passage_id = ANY($1::uuid[])`,
        [allExpectedPassageIds],
      )
    : [];
  const embeddedPassageIds = new Set(embeddingRows.map((r) => r.passage_id));

  const comparisonRows = allExpectedPassageIds.length
    ? await query<ComparisonRow>(
        `SELECT id, report_comparison_id, earlier_passage_id, later_passage_id, alignment_status
         FROM app.current_passage_comparisons
         WHERE earlier_passage_id = ANY($1::uuid[]) OR later_passage_id = ANY($1::uuid[])`,
        [allExpectedPassageIds],
      )
    : [];
  const comparisonsByPassageId = new Map<string, ComparisonRow[]>();
  for (const c of comparisonRows) {
    for (const pid of [c.earlier_passage_id, c.later_passage_id]) {
      if (!pid) continue;
      const arr = comparisonsByPassageId.get(pid) ?? [];
      arr.push(c);
      comparisonsByPassageId.set(pid, arr);
    }
  }

  const rows: ForensicRow[] = [];

  for (const testCase of testCases) {
    const analysis = analyzeQuestion(testCase.question, companies);
    const params = parsePassageSearchParams({
      q: analysis.normalizedQuestion,
      company: analysis.requiredTicker ?? undefined,
      periodStart: analysis.dateRange?.start ?? undefined,
      periodEnd: analysis.dateRange?.end ?? undefined,
      category: analysis.requiredCategory ?? undefined,
    });

    let embedding = null;
    try {
      embedding = await provider.embedQuery(testCase.question);
    } catch (error) {
      console.error(`[embed-query failed] ${testCase.id}: ${(error as Error).message}`);
    }

    const candidates = await generateCandidates(semanticRepo, testCase.question, embedding, params, config, null);
    const strategy = getGateStrategyConfig(config);
    const reranked = enrichWithDirectResponsiveness(
      createQaReranker(config.secondStageReranker).rerank(testCase.question, candidates, analysis),
      analysis,
      strategy,
      strategy.drivesRanking,
    );

    const candidateByPassageId = new Map(candidates.map((c) => [c.passageId, c]));
    const rerankRankByPassageId = new Map(reranked.map((c) => [c.passageId, c.relevanceRank]));

    const uniqueExpectedIds = Array.from(new Set(testCase.minimumSufficientEvidenceSets.flat()));
    if (uniqueExpectedIds.length === 0) continue;

    for (const expectedId of uniqueExpectedIds) {
      const passage = passageById.get(expectedId);
      const reportPassages = passage ? passagesByReport.get(passage.report_id) ?? [] : [];
      const effectiveHeading = passage ? resolveEffectiveHeading(reportPassages, passage.passage_index) : { heading: null, isOwn: false };
      const linkedComparisons = comparisonsByPassageId.get(expectedId) ?? [];
      const vectorAvailable = embeddedPassageIds.has(expectedId);
      const candidate = candidateByPassageId.get(expectedId);
      const mergedPresent = candidate !== undefined;

      const { dependency, recommendation } = diagnose(
        passage,
        effectiveHeading,
        linkedComparisons,
        vectorAvailable,
        mergedPresent,
        testCase.caseType,
      );

      rows.push({
        caseId: testCase.id,
        question: testCase.question,
        expectedPassageIds: uniqueExpectedIds.join("|"),
        expectedRetrievalContextCount: uniqueExpectedIds.length,
        passageLength: passage?.word_count ?? "",
        heading: effectiveHeading.heading ?? "",
        headingIsOwn: effectiveHeading.isOwn,
        previousPassageId: passage ? neighborId(reportPassages, passage.passage_index, -1) : "",
        nextPassageId: passage ? neighborId(reportPassages, passage.passage_index, 1) : "",
        earlierComparisonPassageId: linkedComparisons.map((c) => c.earlier_passage_id ?? "").filter(Boolean).join("|"),
        laterComparisonPassageId: linkedComparisons.map((c) => c.later_passage_id ?? "").filter(Boolean).join("|"),
        comparisonAlignmentStatus: linkedComparisons.map((c) => c.alignment_status).join("|"),
        vectorAvailable,
        currentKeywordRank: candidate?.lexicalRankPosition ?? "",
        currentSemanticRank: candidate?.semanticRawRank ?? "",
        mergedCandidateStatus: mergedPresent ? "PRESENT" : "ABSENT",
        diagnosedDependency: dependency,
        recommendedRepresentation: recommendation,
      });
    }

    void rerankRankByPassageId; // retained for future diagnostic use, not part of this CSV's columns
  }

  const outDir = path.resolve(__dirname, "results");
  mkdirSync(outDir, { recursive: true });
  const header =
    "case_id,question,expected_passage_ids,expected_passage_count,passage_word_count,effective_heading,heading_is_own,previous_passage_id,next_passage_id,earlier_comparison_passage_id,later_comparison_passage_id,comparison_alignment_status,vector_available,current_keyword_rank,current_semantic_rank,merged_candidate_status,diagnosed_dependency,recommended_representation\n";
  const body = rows
    .map((r) =>
      [
        r.caseId,
        csvEscape(r.question),
        r.expectedPassageIds,
        r.expectedRetrievalContextCount,
        r.passageLength,
        csvEscape(r.heading),
        r.headingIsOwn,
        r.previousPassageId,
        r.nextPassageId,
        r.earlierComparisonPassageId,
        r.laterComparisonPassageId,
        r.comparisonAlignmentStatus,
        r.vectorAvailable,
        r.currentKeywordRank,
        r.currentSemanticRank,
        r.mergedCandidateStatus,
        r.diagnosedDependency,
        r.recommendedRepresentation,
      ].join(","),
    )
    .join("\n");
  const outPath = path.join(outDir, "qa_retrieval_miss_forensics.csv");
  writeFileSync(outPath, header + body + "\n");

  console.log(`=== Retrieval-miss forensics (n=${rows.length} passage rows across ${testCases.length} cases) ===`);
  const dependencyCounts = new Map<string, number>();
  for (const r of rows) dependencyCounts.set(r.diagnosedDependency, (dependencyCounts.get(r.diagnosedDependency) ?? 0) + 1);
  for (const [dep, count] of dependencyCounts) console.log(`${dep.padEnd(55)} ${count}`);
  console.log(`\nCSV written to ${outPath}`);

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
