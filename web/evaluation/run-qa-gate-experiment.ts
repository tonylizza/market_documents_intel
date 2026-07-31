/**
 * Milestone 7B.1c Phase 10: bounded configuration experiment. Sweeps the 8
 * predeclared `DirectResponsivenessPreset`s (`lib/config/qa-config.ts`)
 * over the real 74-case `QA_EVALUATION_DATASET`, fixed at the shipped
 * `quality_aware` reranker and `maxEvidenceSetSize=3` (Milestone 7B.1b's
 * own selected defaults -- this experiment is about the gate, not
 * re-litigating reranker/size choices already settled and evaluated).
 *
 * Script (`tsx --tsconfig evaluation/tsconfig.json
 * evaluation/run-qa-gate-experiment.ts`): requires `APP_READONLY_DATABASE_URL`
 * and `QUERY_EMBEDDING_SERVICE_URL` pointed at a running Postgres +
 * embedding service.
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
import { buildEvidenceSet } from "../lib/services/qa/evidence-set-builder";
import { checkCoherence } from "../lib/services/qa/coherence-checker";
import { evaluateGroundedness } from "../lib/services/qa/groundedness-gate";
import { getQaConfig, DIRECT_RESPONSIVENESS_PRESETS, type DirectResponsivenessPreset, type QaConfig } from "../lib/config/qa-config";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { closePool } from "../lib/db/pool";
import { QA_EVALUATION_DATASET, type QaAnswerabilityClass } from "./qa-dataset";
import {
  answerableQuestionCoverage,
  classificationAccuracyFor,
  correctAbstentionRate,
  evidencePrecisionAtK,
  meanOf,
  noAnswerFalseSupportRate,
  percentile,
  rateOf,
  recoveredMinimumSufficientSet,
  type AnswerabilityOutcome,
} from "./qa-metrics";

const PRESETS: DirectResponsivenessPreset[] = [
  "minimal_gate",
  "weighted_gate",
  "weighted_gate_body",
  "query_type_gate",
  "query_type_gate_generic_penalty",
  "full_gate",
  "full_gate_strict_partial",
  "full_gate_restatement_safeguards",
];

/** Milestone 7B.1c "Recommended READY FOR 7B.2 thresholds" -- predeclared
 * before results were inspected, taken verbatim from the milestone plan. */
const READINESS_THRESHOLDS = {
  noAnswerFalseSupportMax: 0.10,
  correctAbstentionMin: 0.85,
  sufficientSetRecoveryMin: 0.70,
  answerableCoverageMin: 0.70,
  precisionAt3Min: 0.25,
  citationCompleteMin: 1.0,
  duplicateMax: 0.0,
};

interface CaseResult {
  caseId: string;
  caseType: string;
  expected: QaAnswerabilityClass;
  actual: AnswerabilityOutcome["actual"];
  selectedIds: string[];
  recovered: boolean;
  precisionAt3: number;
  citationComplete: boolean;
  hasDuplicate: boolean;
  wrongTopicRightCompanyFalseSupport: boolean;
  partiallySupportedCorrect: boolean | null;
  latencyMs: number;
}

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const companyRepo = new PostgresCompanyRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);
  const companies = await companyRepo.listCompanies();

  const resultsByPreset = new Map<DirectResponsivenessPreset, CaseResult[]>();

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
      console.error(`[embed-query failed] ${testCase.id}: ${(error as Error).message}`);
    }

    const baseConfig: QaConfig = { ...getQaConfig(), maxEvidenceSetSize: 3, secondStageReranker: "quality_aware" };
    const candidates = await generateCandidates(semanticRepo, testCase.question, embedding, params, baseConfig, null);
    const baseReranked = createQaReranker("quality_aware").rerank(testCase.question, candidates, analysis);

    const sufficientUnion = new Set(testCase.minimumSufficientEvidenceSets.flat());
    const acceptable = new Set([...sufficientUnion, ...(testCase.acceptableAdditionalPassageIds ?? [])]);
    const trapIds = new Set([
      ...(testCase.unsupportedTrapPassageIds ?? []),
      ...(testCase.numericFragmentTrapPassageIds ?? []),
      ...(testCase.shortHeadingTrapPassageIds ?? []),
    ]);

    for (const preset of PRESETS) {
      const strategy = DIRECT_RESPONSIVENESS_PRESETS[preset];
      const reranked = enrichWithDirectResponsiveness(baseReranked, analysis, strategy, strategy.drivesRanking);
      const evidenceSet = buildEvidenceSet(reranked, analysis, baseConfig);
      const coherence = checkCoherence(evidenceSet.selected, evidenceSet.rejected, analysis);
      const gateDecision = evaluateGroundedness(evidenceSet, analysis, coherence, { ...baseConfig, directResponsivenessPreset: preset });

      const selectedIds = evidenceSet.selected.map((s) => s.passageId);
      const distinctSelectedIds = new Set(selectedIds);
      const wrongTopicRightCompanyFalseSupport =
        gateDecision.status === "SUPPORTED" && selectedIds.some((id) => (testCase.unsupportedTrapPassageIds ?? []).includes(id));

      const list = resultsByPreset.get(preset) ?? [];
      list.push({
        caseId: testCase.id,
        caseType: testCase.caseType,
        expected: testCase.expectedAnswerability,
        actual: gateDecision.status,
        selectedIds,
        recovered: recoveredMinimumSufficientSet(selectedIds, testCase.minimumSufficientEvidenceSets),
        precisionAt3: evidencePrecisionAtK(selectedIds, acceptable, 3),
        citationComplete: gateDecision.signals.citationComplete,
        hasDuplicate: selectedIds.length !== distinctSelectedIds.size,
        wrongTopicRightCompanyFalseSupport,
        partiallySupportedCorrect: testCase.expectedAnswerability === "PARTIALLY_SUPPORTED" ? gateDecision.status === "PARTIALLY_SUPPORTED" : null,
        latencyMs: Date.now() - caseStart,
      });
      resultsByPreset.set(preset, list);
      void trapIds;
    }
  }

  const outDir = path.resolve(__dirname, "results");
  mkdirSync(outDir, { recursive: true });
  const csvHeader = "preset,case_id,case_type,expected,actual,recovered,precision_at_3,citation_complete,has_duplicate,wrong_topic_right_company_false_support\n";
  const csvBody: string[] = [];

  console.log("=== Phase 10: bounded direct-responsiveness gate-strategy grid (n=74 per preset) ===\n");
  const summaries: { preset: DirectResponsivenessPreset; meetsAllThresholds: boolean; metrics: Record<string, number> }[] = [];

  for (const preset of PRESETS) {
    const results = resultsByPreset.get(preset) ?? [];
    for (const r of results) {
      csvBody.push([preset, r.caseId, r.caseType, r.expected, r.actual, r.recovered, r.precisionAt3.toFixed(4), r.citationComplete, r.hasDuplicate, r.wrongTopicRightCompanyFalseSupport].join(","));
    }

    const outcomes: AnswerabilityOutcome[] = results.map((r) => ({ caseId: r.caseId, expected: r.expected, actual: r.actual }));
    const answerable = results.filter((r) => r.expected === "SUPPORTED" || r.expected === "PARTIALLY_SUPPORTED");
    const partialCases = results.filter((r) => r.partiallySupportedCorrect !== null);

    const metrics = {
      noAnswerFalseSupport: noAnswerFalseSupportRate(outcomes),
      correctAbstention: correctAbstentionRate(outcomes),
      sufficientSetRecovery: answerableQuestionCoverage(answerable.map((r) => r.recovered)),
      answerableCoverage: answerableQuestionCoverage(answerable.map((r) => r.recovered)),
      precisionAt3: meanOf(results.map((r) => r.precisionAt3)),
      citationComplete: rateOf(results.map((r) => r.citationComplete)),
      duplicateRate: rateOf(results.map((r) => r.hasDuplicate)),
      wrongTopicRightCompanyFalseSupport: rateOf(results.map((r) => r.wrongTopicRightCompanyFalseSupport)),
      partialSupportPrecision: partialCases.length > 0 ? rateOf(partialCases.map((r) => r.partiallySupportedCorrect === true)) : 1,
      ambiguousAccuracy: classificationAccuracyFor(outcomes, "AMBIGUOUS_OR_CONFLICTING"),
      latencyP50: percentile(results.map((r) => r.latencyMs), 50),
    };

    const meetsAllThresholds =
      metrics.noAnswerFalseSupport <= READINESS_THRESHOLDS.noAnswerFalseSupportMax &&
      metrics.correctAbstention >= READINESS_THRESHOLDS.correctAbstentionMin &&
      metrics.sufficientSetRecovery >= READINESS_THRESHOLDS.sufficientSetRecoveryMin &&
      metrics.answerableCoverage >= READINESS_THRESHOLDS.answerableCoverageMin &&
      metrics.precisionAt3 >= READINESS_THRESHOLDS.precisionAt3Min &&
      metrics.citationComplete >= READINESS_THRESHOLDS.citationCompleteMin &&
      metrics.duplicateRate <= READINESS_THRESHOLDS.duplicateMax;

    summaries.push({ preset, meetsAllThresholds, metrics });

    console.log(
      `${preset.padEnd(34)} meetsAll=${meetsAllThresholds ? "YES" : "no "} ` +
        `falseSupport=${metrics.noAnswerFalseSupport.toFixed(3)} abstention=${metrics.correctAbstention.toFixed(3)} ` +
        `recovery=${metrics.sufficientSetRecovery.toFixed(3)} p@3=${metrics.precisionAt3.toFixed(3)} ` +
        `wrongTopicFalseSupport=${metrics.wrongTopicRightCompanyFalseSupport.toFixed(3)} partialPrecision=${metrics.partialSupportPrecision.toFixed(3)} ` +
        `ambiguousAcc=${metrics.ambiguousAccuracy.toFixed(3)} citationComplete=${metrics.citationComplete.toFixed(3)} dup=${metrics.duplicateRate.toFixed(3)} ` +
        `latencyP50=${metrics.latencyP50.toFixed(0)}ms`,
    );
  }

  writeFileSync(path.join(outDir, "qa_gate_strategy_experiment.csv"), csvHeader + csvBody.join("\n") + "\n");

  console.log("\n=== Selection ===");
  const eligible = summaries.filter((s) => s.meetsAllThresholds);
  if (eligible.length > 0) {
    // Smallest/simplest preset (earliest in the predeclared ladder) that
    // clears every threshold.
    const selected = PRESETS.find((p) => eligible.some((e) => e.preset === p))!;
    console.log(`selected preset: ${selected} (smallest/simplest preset clearing every predeclared threshold)`);
  } else {
    console.log("no preset met every predeclared READY-FOR-7B.2 threshold -- NOT READY FOR 7B.2 (see final report for dominant failure stage and recommended next experiment).");
    const best = [...summaries].sort((a, b) => (b.metrics.precisionAt3 + b.metrics.sufficientSetRecovery) - (a.metrics.precisionAt3 + a.metrics.sufficientSetRecovery))[0];
    console.log(`closest preset by (precision@3 + sufficientSetRecovery): ${best.preset}`);
  }

  console.log(`\nCSV written to ${path.join(outDir, "qa_gate_strategy_experiment.csv")}`);
  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
