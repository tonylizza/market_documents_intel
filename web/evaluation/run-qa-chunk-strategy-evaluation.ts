/**
 * Milestone 7B.1d Phase 9-10: reruns the same 74-case `QA_EVALUATION_DATASET`
 * under the canonical-only baseline and each built Q&A retrieval-chunk
 * strategy (individually and combined), using the shipped default reranker
 * (`getQaConfig().secondStageReranker`) and evidence-set size -- this is a
 * chunk-strategy comparison, not a reranker/size sweep (that's
 * `run-qa-evaluation.ts`'s job, unchanged by this script).
 *
 * Requires `APP_READONLY_DATABASE_URL` and `QUERY_EMBEDDING_SERVICE_URL`
 * (same as `run-qa-failure-attribution.ts`), plus a populated
 * `qa_experiment.retrieval_chunks` table (`market_documents.qa_experiment.
 * build_chunks`) for the strategy configs to have any effect -- run against
 * the canonical-only baseline alone if that table is empty/absent.
 *
 * Script: `tsx --tsconfig evaluation/tsconfig.json
 * evaluation/run-qa-chunk-strategy-evaluation.ts`
 */
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { PostgresSemanticRetrievalRepository } from "../lib/repositories/postgres-semantic-retrieval-repository";
import { PostgresCompanyRepository } from "../lib/repositories/postgres-company-repository";
import { QaChunkRetrievalRepository } from "../lib/repositories/qa-chunk-retrieval-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "../lib/services/query-embedding-provider";
import { analyzeQuestion } from "../lib/services/qa/query-analysis";
import { generateCandidates, type ChunkCandidateOptions } from "../lib/services/qa/candidate-generation";
import { createQaReranker } from "../lib/services/qa/qa-reranker";
import { enrichWithDirectResponsiveness } from "../lib/services/qa/direct-responsiveness";
import { buildEvidenceSet, EXAMINATION_WINDOW_MULTIPLIER } from "../lib/services/qa/evidence-set-builder";
import { checkCoherence } from "../lib/services/qa/coherence-checker";
import { evaluateGroundedness } from "../lib/services/qa/groundedness-gate";
import { getQaConfig, getGateStrategyConfig } from "../lib/config/qa-config";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { closePool } from "../lib/db/pool";
import { QA_EVALUATION_DATASET } from "./qa-dataset";
import {
  evidencePrecisionAtK,
  evidenceRecallAtK,
  recoveredMinimumSufficientSet,
  correctAbstentionRate,
  noAnswerFalseSupportRate,
  rateOf,
  percentile,
  type AnswerabilityOutcome,
} from "./qa-metrics";
import { classifyFailureStage, probeSufficientSet, type FailureStage } from "./qa-failure-attribution";

const CHUNK_STRATEGIES = [
  "HEADING_PLUS_PASSAGE",
  "PREVIOUS_PLUS_CURRENT",
  "CURRENT_PLUS_NEXT",
  "LOCAL_WINDOW",
  "FIXED_TOKEN_WINDOW_256_64",
  "COMPARISON_PAIR",
] as const;

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

interface StrategyConfig {
  label: string;
  chunkOptions: ChunkCandidateOptions | undefined;
}

interface CaseResult {
  configLabel: string;
  caseId: string;
  caseType: string;
  expected: string;
  actual: string;
  primaryStage: FailureStage;
  recovered: boolean;
  precisionAt3: number;
  recallAt5: number;
  hasDuplicatePassageId: boolean;
  citationComplete: boolean;
  latencyMs: number;
  wasRetrievalMissBaselineCase: boolean;
}

interface ConfigSummary {
  label: string;
  n: number;
  retrievalMissCount: number;
  retrievalMissAmongBaseline13: number;
  sufficientSetRecoveryRate: number;
  precisionAt3Mean: number;
  recallAt5Mean: number;
  noAnswerFalseSupportRate: number;
  correctAbstentionRate: number;
  citationCompletenessRate: number;
  duplicateEvidenceRate: number;
  latencyP50: number;
  latencyP95: number;
  readyForNextPhase: boolean;
  readinessFailures: string[];
}

async function runConfig(
  config: StrategyConfig,
  semanticRepo: PostgresSemanticRetrievalRepository,
  companies: Awaited<ReturnType<PostgresCompanyRepository["listCompanies"]>>,
  provider: HttpQueryEmbeddingProvider,
): Promise<CaseResult[]> {
  const qaConfig = getQaConfig();
  const examinationWindow = qaConfig.maxEvidenceSetSize * EXAMINATION_WINDOW_MULTIPLIER;
  const results: CaseResult[] = [];

  for (const testCase of QA_EVALUATION_DATASET) {
    const caseStart = Date.now();
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
      console.error(`[embed-query failed] ${config.label}/${testCase.id}: ${(error as Error).message}`);
    }

    const candidates = await generateCandidates(semanticRepo, testCase.question, embedding, params, qaConfig, null, config.chunkOptions);
    const candidatePassageIds = new Set(candidates.map((c) => c.passageId));

    const baseReranked = createQaReranker(qaConfig.secondStageReranker).rerank(testCase.question, candidates, analysis);
    const strategy = getGateStrategyConfig(qaConfig);
    const reranked = enrichWithDirectResponsiveness(baseReranked, analysis, strategy, strategy.drivesRanking);
    const rankByPassageId = new Map(reranked.map((c) => [c.passageId, c.relevanceRank]));

    const evidenceSet = buildEvidenceSet(reranked, analysis, qaConfig);
    const coherence = checkCoherence(evidenceSet.selected, evidenceSet.rejected, analysis);
    const gateDecision = evaluateGroundedness(evidenceSet, analysis, coherence, qaConfig);

    const selectedIds = evidenceSet.selected.map((s) => s.passageId);
    const distinctSelectedIds = new Set(selectedIds);
    const sufficientUnion = new Set(testCase.minimumSufficientEvidenceSets.flat());
    const acceptable = new Set([...sufficientUnion, ...(testCase.acceptableAdditionalPassageIds ?? [])]);

    const setProbes = testCase.minimumSufficientEvidenceSets.map((set) =>
      probeSufficientSet(set, candidatePassageIds, rankByPassageId, examinationWindow),
    );
    const recovered = recoveredMinimumSufficientSet(selectedIds, testCase.minimumSufficientEvidenceSets);
    const primaryStage = classifyFailureStage({
      expected: testCase.expectedAnswerability,
      actual: gateDecision.status,
      sufficientSets: testCase.minimumSufficientEvidenceSets,
      setProbes,
      recovered,
    });

    results.push({
      configLabel: config.label,
      caseId: testCase.id,
      caseType: testCase.caseType,
      expected: testCase.expectedAnswerability,
      actual: gateDecision.status,
      primaryStage,
      recovered,
      precisionAt3: evidencePrecisionAtK(selectedIds, acceptable, 3),
      recallAt5: evidenceRecallAtK(selectedIds, sufficientUnion, 5),
      hasDuplicatePassageId: selectedIds.length !== distinctSelectedIds.size,
      citationComplete: gateDecision.signals.citationComplete,
      latencyMs: Date.now() - caseStart,
      wasRetrievalMissBaselineCase: RETRIEVAL_MISS_CASE_IDS.has(testCase.id),
    });
  }

  return results;
}

function summarize(label: string, results: readonly CaseResult[]): ConfigSummary {
  const answerable = results.filter((r) => r.expected !== "INSUFFICIENT_EVIDENCE");
  const outcomes: AnswerabilityOutcome[] = results.map((r) => ({ caseId: r.caseId, expected: r.expected as AnswerabilityOutcome["expected"], actual: r.actual as AnswerabilityOutcome["actual"] }));

  const retrievalMissCount = results.filter((r) => r.primaryStage === "RETRIEVAL_MISS").length;
  const retrievalMissAmongBaseline13 = results.filter((r) => r.wasRetrievalMissBaselineCase && r.primaryStage === "RETRIEVAL_MISS").length;
  const sufficientSetRecoveryRate = rateOf(answerable.map((r) => r.recovered));
  const precisionAt3Mean = answerable.length > 0 ? answerable.reduce((s, r) => s + r.precisionAt3, 0) / answerable.length : 0;
  const recallAt5Mean = answerable.length > 0 ? answerable.reduce((s, r) => s + r.recallAt5, 0) / answerable.length : 0;
  const latencies = results.map((r) => r.latencyMs);

  const summary: ConfigSummary = {
    label,
    n: results.length,
    retrievalMissCount,
    retrievalMissAmongBaseline13,
    sufficientSetRecoveryRate,
    precisionAt3Mean,
    recallAt5Mean,
    noAnswerFalseSupportRate: noAnswerFalseSupportRate(outcomes),
    correctAbstentionRate: correctAbstentionRate(outcomes),
    citationCompletenessRate: rateOf(results.map((r) => r.citationComplete)),
    duplicateEvidenceRate: rateOf(results.map((r) => r.hasDuplicatePassageId)),
    latencyP50: percentile(latencies, 50),
    latencyP95: percentile(latencies, 95),
    readyForNextPhase: false,
    readinessFailures: [],
  };

  // Predeclared Milestone 7B.1d readiness thresholds (brief Phase 10) --
  // applied identically to every config, never adjusted after seeing
  // results.
  const failures: string[] = [];
  if (summary.retrievalMissCount > 5) failures.push(`RETRIEVAL_MISS ${summary.retrievalMissCount} > 5`);
  if (summary.sufficientSetRecoveryRate < 0.7) failures.push(`sufficient-set recovery ${(summary.sufficientSetRecoveryRate * 100).toFixed(1)}% < 70%`);
  if (summary.precisionAt3Mean < 0.25) failures.push(`precision@3 ${summary.precisionAt3Mean.toFixed(3)} < 0.25`);
  if (summary.noAnswerFalseSupportRate > 0.1) failures.push(`no-answer false-support ${(summary.noAnswerFalseSupportRate * 100).toFixed(1)}% > 10%`);
  if (summary.correctAbstentionRate < 0.85) failures.push(`correct abstention ${(summary.correctAbstentionRate * 100).toFixed(1)}% < 85%`);
  if (summary.citationCompletenessRate < 1.0) failures.push(`citation completeness ${(summary.citationCompletenessRate * 100).toFixed(1)}% < 100%`);
  if (summary.duplicateEvidenceRate > 0.0) failures.push(`duplicate evidence ${(summary.duplicateEvidenceRate * 100).toFixed(1)}% > 0%`);
  summary.readinessFailures = failures;
  summary.readyForNextPhase = failures.length === 0;
  return summary;
}

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const chunkRepo = new QaChunkRetrievalRepository();
  const companyRepo = new PostgresCompanyRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);

  const companies = await companyRepo.listCompanies();

  // Milestone 7B.1d Phase 9 finding (debug run against the live corpus):
  // `qa_experiment.retrieval_chunks` holds ~93,554 rows across 6 strategies
  // -- roughly 4.2x the canonical passage count -- so reusing the canonical
  // `candidateLimitPerSource` (40) as the chunk child-candidate limit left
  // known-answerable passages ranked just outside the cutoff (e.g. rank 68
  // for a verified RETRIEVAL_MISS case) even though chunk retrieval had
  // genuinely surfaced them. `CHUNK_CHILD_LIMIT`/`COMBINED_CHUNK_CHILD_LIMIT`
  // are sized to the larger candidate pool, not copied from the canonical
  // config.
  const CHUNK_CHILD_LIMIT = 150;
  const COMBINED_CHUNK_CHILD_LIMIT = 300;

  const configs: StrategyConfig[] = [
    { label: "BASELINE_CANONICAL", chunkOptions: undefined },
    ...CHUNK_STRATEGIES.map((strategy): StrategyConfig => ({
      label: strategy,
      chunkOptions: { repo: chunkRepo, strategies: [strategy], childLimit: CHUNK_CHILD_LIMIT },
    })),
    {
      label: "ALL_STRATEGIES_COMBINED",
      chunkOptions: { repo: chunkRepo, strategies: CHUNK_STRATEGIES, childLimit: COMBINED_CHUNK_CHILD_LIMIT },
    },
  ];

  const allResults: CaseResult[] = [];
  const summaries: ConfigSummary[] = [];

  for (const config of configs) {
    console.log(`\n=== Running config: ${config.label} ===`);
    const results = await runConfig(config, semanticRepo, companies, provider);
    allResults.push(...results);
    const summary = summarize(config.label, results);
    summaries.push(summary);
    console.log(
      `  RETRIEVAL_MISS=${summary.retrievalMissCount} (of baseline-13: ${summary.retrievalMissAmongBaseline13}) ` +
        `recovery=${(summary.sufficientSetRecoveryRate * 100).toFixed(1)}% precision@3=${summary.precisionAt3Mean.toFixed(3)} ` +
        `abstention=${(summary.correctAbstentionRate * 100).toFixed(1)}% falseSupport=${(summary.noAnswerFalseSupportRate * 100).toFixed(1)}% ` +
        `citationComplete=${(summary.citationCompletenessRate * 100).toFixed(1)}% dupEvidence=${(summary.duplicateEvidenceRate * 100).toFixed(1)}% ` +
        `READY=${summary.readyForNextPhase}`,
    );
    if (!summary.readyForNextPhase) {
      console.log(`  Failures: ${summary.readinessFailures.join("; ")}`);
    }
  }

  const outDir = path.resolve(__dirname, "results");
  mkdirSync(outDir, { recursive: true });

  const caseHeader = "config_label,case_id,case_type,expected,actual,primary_stage,recovered,precision_at_3,recall_at_5,has_duplicate_passage_id,citation_complete,latency_ms,was_retrieval_miss_baseline_case\n";
  const caseBody = allResults
    .map((r) =>
      [r.configLabel, r.caseId, r.caseType, r.expected, r.actual, r.primaryStage, r.recovered, r.precisionAt3.toFixed(3), r.recallAt5.toFixed(3), r.hasDuplicatePassageId, r.citationComplete, r.latencyMs, r.wasRetrievalMissBaselineCase].join(","),
    )
    .join("\n");
  writeFileSync(path.join(outDir, "qa_chunk_strategy_case_results.csv"), caseHeader + caseBody + "\n");

  const summaryHeader = "label,n,retrieval_miss_count,retrieval_miss_among_baseline_13,sufficient_set_recovery_rate,precision_at_3_mean,recall_at_5_mean,no_answer_false_support_rate,correct_abstention_rate,citation_completeness_rate,duplicate_evidence_rate,latency_p50,latency_p95,ready_for_next_phase,readiness_failures\n";
  const summaryBody = summaries
    .map((s) =>
      [
        s.label,
        s.n,
        s.retrievalMissCount,
        s.retrievalMissAmongBaseline13,
        s.sufficientSetRecoveryRate.toFixed(4),
        s.precisionAt3Mean.toFixed(4),
        s.recallAt5Mean.toFixed(4),
        s.noAnswerFalseSupportRate.toFixed(4),
        s.correctAbstentionRate.toFixed(4),
        s.citationCompletenessRate.toFixed(4),
        s.duplicateEvidenceRate.toFixed(4),
        s.latencyP50,
        s.latencyP95,
        s.readyForNextPhase,
        `"${s.readinessFailures.join("; ")}"`,
      ].join(","),
    )
    .join("\n");
  writeFileSync(path.join(outDir, "qa_chunk_strategy_summary.csv"), summaryHeader + summaryBody + "\n");

  console.log(`\nCSVs written to ${outDir}`);
  const anyReady = summaries.some((s) => s.readyForNextPhase);
  console.log(`\n${anyReady ? "READY FOR 7B.2" : "NOT READY FOR 7B.2"} (best config: ${summaries.slice().sort((a, b) => a.retrievalMissCount - b.retrievalMissCount)[0]?.label})`);

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
