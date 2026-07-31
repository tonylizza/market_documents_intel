/**
 * Milestone 7B.1b Q&A evidence-selection/groundedness-gate evaluation
 * runner. Executes the real 74-case `QA_EVALUATION_DATASET` against the
 * live corpus + live query-embedding service -- a script (`tsx
 * --tsconfig evaluation/tsconfig.json evaluation/run-qa-evaluation.ts`),
 * not a unit test: requires `APP_READONLY_DATABASE_URL` and
 * `QUERY_EMBEDDING_SERVICE_URL` pointed at a running Postgres + embedding
 * service.
 *
 * For each case: analyzes the question once, embeds it once, fetches
 * candidates once, then sweeps all 3 rerankers x all 3 evidence-set sizes
 * (9 combinations) purely in-memory over that same candidate set -- no
 * repeated DB/embedding round trips per combination.
 *
 * Selection gate declared here, before results are inspected:
 * - reranker: highest answerableQuestionCoverage among rerankers with
 *   noAnswerFalseSupportRate <= 0.10 and citationCompleteness == 1.0;
 * - evidence-set size: smallest size (3/5/8) that does not reduce
 *   answerableQuestionCoverage by more than 5 percentage points versus the
 *   largest size tested, and keeps evidenceSetRedundancy from rising.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { PostgresSemanticRetrievalRepository } from "../lib/repositories/postgres-semantic-retrieval-repository";
import { PostgresCompanyRepository } from "../lib/repositories/postgres-company-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "../lib/services/query-embedding-provider";
import { analyzeQuestion } from "../lib/services/qa/query-analysis";
import { generateCandidates } from "../lib/services/qa/candidate-generation";
import { createQaReranker } from "../lib/services/qa/qa-reranker";
import { buildEvidenceSet } from "../lib/services/qa/evidence-set-builder";
import { checkCoherence } from "../lib/services/qa/coherence-checker";
import { evaluateGroundedness } from "../lib/services/qa/groundedness-gate";
import { getQaConfig, getGateStrategyConfig } from "../lib/config/qa-config";
import { enrichWithDirectResponsiveness } from "../lib/services/qa/direct-responsiveness";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { closePool } from "../lib/db/pool";
import type { PassageSearchParams } from "../lib/domain/passage";
import type { QaRerankerMethod } from "../lib/domain/qa-evidence";
import { QA_EVALUATION_DATASET, type QaAnswerabilityClass } from "./qa-dataset";
import {
  accuracyByGroup,
  answerableQuestionCoverage,
  classificationAccuracyFor,
  correctAbstentionRate,
  duplicateEvidenceRate,
  evidencePrecisionAtK,
  evidenceRecallAtK,
  meanOf,
  noAnswerFalseSupportRate,
  numericFragmentMisuseRate,
  percentile,
  rateOf,
  recoveredMinimumSufficientSet,
  unsupportedEvidenceRate,
  type AnswerabilityOutcome,
} from "./qa-metrics";

const RERANKER_METHODS: QaRerankerMethod[] = ["baseline", "concept_coverage", "quality_aware"];
const EVIDENCE_SET_SIZES = [3, 5, 8];

function buildParams(analysis: ReturnType<typeof analyzeQuestion>): PassageSearchParams {
  return parsePassageSearchParams({
    q: analysis.normalizedQuestion,
    company: analysis.requiredTicker ?? undefined,
    periodStart: analysis.dateRange?.start ?? undefined,
    periodEnd: analysis.dateRange?.end ?? undefined,
    category: analysis.requiredCategory ?? undefined,
  });
}

interface CaseRunResult {
  caseId: string;
  caseType: string;
  companyTicker?: string;
  questionType: string;
  reranker: QaRerankerMethod;
  evidenceSetSize: number;
  expected: QaAnswerabilityClass;
  actual: AnswerabilityOutcome["actual"];
  selectedPassageIds: string[];
  precisionAt3: number;
  precisionAt5: number;
  recallAt5: number;
  recovered: boolean;
  selectedATrap: boolean;
  hasDuplicatePassageId: boolean;
  suppliedFragmentOnly: boolean;
  citationComplete: boolean;
  redundancyRatio: number;
  latencyMs: number;
}

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const companyRepo = new PostgresCompanyRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);

  const companies = await companyRepo.listCompanies();
  const results: CaseRunResult[] = [];
  let providerFailures = 0;

  for (const testCase of QA_EVALUATION_DATASET) {
    const caseStart = Date.now();
    const analysis = analyzeQuestion(testCase.question, companies);
    const params = buildParams(analysis);

    let embedding = null;
    try {
      embedding = await provider.embedQuery(testCase.question);
    } catch (error) {
      providerFailures += 1;
      console.error(`[embed-query failed] ${testCase.id}: ${(error as Error).message}`);
    }

    const candidates = await generateCandidates(semanticRepo, testCase.question, embedding, params, getQaConfig(), null);

    const sufficientUnion = new Set(testCase.minimumSufficientEvidenceSets.flat());
    const acceptable = new Set([...sufficientUnion, ...(testCase.acceptableAdditionalPassageIds ?? [])]);
    const trapIds = new Set([
      ...(testCase.unsupportedTrapPassageIds ?? []),
      ...(testCase.numericFragmentTrapPassageIds ?? []),
      ...(testCase.shortHeadingTrapPassageIds ?? []),
    ]);

    for (const method of RERANKER_METHODS) {
      const baseReranked = createQaReranker(method).rerank(testCase.question, candidates, analysis);

      for (const size of EVIDENCE_SET_SIZES) {
        const config = { ...getQaConfig(), maxEvidenceSetSize: size };
        // Milestone 7B.1c: direct-responsiveness enrichment runs
        // unconditionally, same as production (`qa-pipeline.ts`) -- this
        // sweep otherwise still tests the pre-7B.1c reranker/size grid.
        const strategy = getGateStrategyConfig(config);
        const reranked = enrichWithDirectResponsiveness(baseReranked, analysis, strategy, strategy.drivesRanking);
        const evidenceSet = buildEvidenceSet(reranked, analysis, config);
        const coherence = checkCoherence(evidenceSet.selected, evidenceSet.rejected, analysis);
        const gateDecision = evaluateGroundedness(evidenceSet, analysis, coherence, config);

        const selectedIds = evidenceSet.selected.map((s) => s.passageId);
        const distinctSelectedIds = new Set(selectedIds);

        results.push({
          caseId: testCase.id,
          caseType: testCase.caseType,
          companyTicker: testCase.companyTicker,
          questionType: analysis.questionType,
          reranker: method,
          evidenceSetSize: size,
          expected: testCase.expectedAnswerability,
          actual: gateDecision.status,
          selectedPassageIds: selectedIds,
          precisionAt3: evidencePrecisionAtK(selectedIds, acceptable, 3),
          precisionAt5: evidencePrecisionAtK(selectedIds, acceptable, 5),
          recallAt5: evidenceRecallAtK(selectedIds, sufficientUnion, 5),
          recovered: recoveredMinimumSufficientSet(selectedIds, testCase.minimumSufficientEvidenceSets),
          selectedATrap: selectedIds.some((id) => trapIds.has(id)),
          hasDuplicatePassageId: selectedIds.length !== distinctSelectedIds.size,
          suppliedFragmentOnly: gateDecision.status === "SUPPORTED" && evidenceSet.selected.every((s) => s.numericFragmentSeverity === "fragment_without_context") && evidenceSet.selected.length > 0,
          citationComplete: gateDecision.signals.citationComplete,
          redundancyRatio: gateDecision.signals.redundancyRatio,
          latencyMs: Date.now() - caseStart,
        });
      }
    }
  }

  const outDir = path.resolve(__dirname, "results");
  mkdirSync(outDir, { recursive: true });
  const csvHeader = "case_id,case_type,reranker,evidence_set_size,expected,actual,recovered,precision_at_3,precision_at_5,recall_at_5,selected_a_trap,citation_complete,redundancy_ratio\n";
  const csvBody = results
    .map((r) =>
      [
        r.caseId,
        r.caseType,
        r.reranker,
        r.evidenceSetSize,
        r.expected,
        r.actual,
        r.recovered,
        r.precisionAt3.toFixed(4),
        r.precisionAt5.toFixed(4),
        r.recallAt5.toFixed(4),
        r.selectedATrap,
        r.citationComplete,
        r.redundancyRatio.toFixed(4),
      ].join(","),
    )
    .join("\n");
  writeFileSync(path.join(outDir, "qa_evidence_evaluation.csv"), csvHeader + csvBody + "\n");

  function summarize(label: string, subset: CaseRunResult[]) {
    const outcomes: AnswerabilityOutcome[] = subset.map((r) => ({ caseId: r.caseId, expected: r.expected, actual: r.actual }));
    const answerable = subset.filter((r) => r.expected === "SUPPORTED" || r.expected === "PARTIALLY_SUPPORTED");
    console.log(
      `${label.padEnd(28)} n=${subset.length} ` +
        `abstention=${correctAbstentionRate(outcomes).toFixed(3)} falseSupport=${noAnswerFalseSupportRate(outcomes).toFixed(3)} ` +
        `partialAcc=${classificationAccuracyFor(outcomes, "PARTIALLY_SUPPORTED").toFixed(3)} ambiguousAcc=${classificationAccuracyFor(outcomes, "AMBIGUOUS_OR_CONFLICTING").toFixed(3)} ` +
        `coverage=${answerableQuestionCoverage(answerable.map((r) => r.recovered)).toFixed(3)} ` +
        `p@3=${meanOf(subset.map((r) => r.precisionAt3)).toFixed(3)} p@5=${meanOf(subset.map((r) => r.precisionAt5)).toFixed(3)} recall@5=${meanOf(subset.map((r) => r.recallAt5)).toFixed(3)} ` +
        `unsupportedRate=${unsupportedEvidenceRate(subset.map((r) => r.selectedATrap)).toFixed(3)} dupRate=${duplicateEvidenceRate(subset.map((r) => r.hasDuplicatePassageId)).toFixed(3)} ` +
        `numericMisuse=${numericFragmentMisuseRate(subset.map((r) => r.suppliedFragmentOnly)).toFixed(3)} citationComplete=${rateOf(subset.map((r) => r.citationComplete)).toFixed(3)} ` +
        `redundancy=${meanOf(subset.map((r) => r.redundancyRatio)).toFixed(3)} latencyP50=${percentile(subset.map((r) => r.latencyMs), 50).toFixed(0)}ms`,
    );
  }

  console.log("\n=== By reranker (evidence-set size = 5) ===");
  for (const method of RERANKER_METHODS) {
    summarize(method, results.filter((r) => r.reranker === method && r.evidenceSetSize === 5));
  }

  console.log("\n=== By evidence-set size (reranker = quality_aware) ===");
  for (const size of EVIDENCE_SET_SIZES) {
    summarize(`size=${size}`, results.filter((r) => r.reranker === "quality_aware" && r.evidenceSetSize === size));
  }

  console.log("\n=== By case type (reranker = quality_aware, size = 5) ===");
  const baseline = results.filter((r) => r.reranker === "quality_aware" && r.evidenceSetSize === 5);
  const caseTypes = [...new Set(baseline.map((r) => r.caseType))].sort();
  for (const caseType of caseTypes) {
    summarize(caseType, baseline.filter((r) => r.caseType === caseType));
  }

  console.log("\n=== Gate calibration by question type (reranker = quality_aware, size = 5) ===");
  const byQuestionType = accuracyByGroup(baseline.map((r) => ({ caseId: r.caseId, expected: r.expected, actual: r.actual, group: r.questionType })));
  for (const g of byQuestionType) {
    console.log(`${g.group.padEnd(20)} n=${g.caseCount} accuracy=${g.accuracy.toFixed(3)}`);
  }

  // --- predeclared selection gate ---
  console.log("\n=== Reranker selection gate (predeclared) ===");
  const rerankerCandidates = RERANKER_METHODS.map((method) => {
    const subset = results.filter((r) => r.reranker === method && r.evidenceSetSize === 5);
    const outcomes: AnswerabilityOutcome[] = subset.map((r) => ({ caseId: r.caseId, expected: r.expected, actual: r.actual }));
    const answerable = subset.filter((r) => r.expected === "SUPPORTED" || r.expected === "PARTIALLY_SUPPORTED");
    return {
      method,
      coverage: answerableQuestionCoverage(answerable.map((r) => r.recovered)),
      falseSupport: noAnswerFalseSupportRate(outcomes),
      citationComplete: rateOf(subset.map((r) => r.citationComplete)),
    };
  });
  const eligibleRerankers = rerankerCandidates.filter((c) => c.falseSupport <= 0.1 && c.citationComplete === 1);
  eligibleRerankers.sort((a, b) => b.coverage - a.coverage);
  console.log(`candidates: ${rerankerCandidates.map((c) => `${c.method}(coverage=${c.coverage.toFixed(3)},falseSupport=${c.falseSupport.toFixed(3)})`).join(", ")}`);
  if (eligibleRerankers.length === 0) {
    console.log("no reranker satisfied the gate (falseSupport<=0.10, citationComplete=1.0) -- falling back to quality_aware (default)");
  } else {
    console.log(`selected reranker: ${eligibleRerankers[0].method}`);
  }

  console.log("\n=== Evidence-set size selection gate (predeclared) ===");
  const sizeCandidates = EVIDENCE_SET_SIZES.map((size) => {
    const subset = results.filter((r) => r.reranker === "quality_aware" && r.evidenceSetSize === size);
    const answerable = subset.filter((r) => r.expected === "SUPPORTED" || r.expected === "PARTIALLY_SUPPORTED");
    return {
      size,
      coverage: answerableQuestionCoverage(answerable.map((r) => r.recovered)),
      redundancy: meanOf(subset.map((r) => r.redundancyRatio)),
    };
  });
  const maxCoverage = Math.max(...sizeCandidates.map((c) => c.coverage));
  const eligibleSizes = sizeCandidates.filter((c) => maxCoverage - c.coverage <= 0.05).sort((a, b) => a.size - b.size);
  console.log(`candidates: ${sizeCandidates.map((c) => `size=${c.size}(coverage=${c.coverage.toFixed(3)},redundancy=${c.redundancy.toFixed(3)})`).join(", ")}`);
  console.log(`selected evidence-set size: ${eligibleSizes[0]?.size ?? 5}`);

  console.log(`\nquery-embedding provider failures: ${providerFailures}/${QA_EVALUATION_DATASET.length}`);
  console.log(`CSV written to ${path.join(outDir, "qa_evidence_evaluation.csv")}`);

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
