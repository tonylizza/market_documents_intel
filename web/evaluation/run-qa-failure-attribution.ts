/**
 * Milestone 7B.1c Phase 1: baseline failure attribution for the 74-case
 * `QA_EVALUATION_DATASET`, run once at the shipped default config
 * (`quality_aware` reranker, `maxEvidenceSetSize=3` -- `getQaConfig()`'s
 * actual defaults, not a swept parameter) so this is a diagnosis of what
 * ships today, not of some other configuration.
 *
 * Script (`tsx --tsconfig evaluation/tsconfig.json
 * evaluation/run-qa-failure-attribution.ts`), not a unit test: requires
 * `APP_READONLY_DATABASE_URL` and `QUERY_EMBEDDING_SERVICE_URL` pointed at
 * a running Postgres + embedding service, same as `run-qa-evaluation.ts`.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { PostgresSemanticRetrievalRepository } from "../lib/repositories/postgres-semantic-retrieval-repository";
import { PostgresCompanyRepository } from "../lib/repositories/postgres-company-repository";
import { HttpQueryEmbeddingProvider, loadHttpQueryEmbeddingProviderConfig } from "../lib/services/query-embedding-provider";
import { analyzeQuestion } from "../lib/services/qa/query-analysis";
import { generateCandidates } from "../lib/services/qa/candidate-generation";
import { createQaReranker } from "../lib/services/qa/qa-reranker";
import { buildEvidenceSet, EXAMINATION_WINDOW_MULTIPLIER } from "../lib/services/qa/evidence-set-builder";
import { checkCoherence } from "../lib/services/qa/coherence-checker";
import { evaluateGroundedness } from "../lib/services/qa/groundedness-gate";
import { getQaConfig, getGateStrategyConfig } from "../lib/config/qa-config";
import { enrichWithDirectResponsiveness } from "../lib/services/qa/direct-responsiveness";
import { parsePassageSearchParams } from "../lib/services/passage-search-params";
import { closePool } from "../lib/db/pool";
import { QA_EVALUATION_DATASET } from "./qa-dataset";
import { recoveredMinimumSufficientSet } from "./qa-metrics";
import { classifyFailureStage, probeSufficientSet, type FailureStage } from "./qa-failure-attribution";

/**
 * Manual `GROUND_TRUTH_AMBIGUITY` overrides -- applied *after* reading the
 * deterministic classification's output and the case's own `notes` field,
 * never auto-detected (see `qa-failure-attribution.ts`'s module doc). Each
 * entry documents the specific reason the expected set/status itself looks
 * incomplete, overly narrow, or genuinely ambiguous, distinct from a
 * pipeline defect.
 */
const GROUND_TRUTH_REVIEW_OVERRIDES: Record<string, string> = {
  "partial-sbp-remuneration-and-succession":
    "Dataset's own notes admit succession-planning content was never verified present or absent in the corpus (\"no succession-planning passage was found ... in this inspection\") -- the expected PARTIALLY_SUPPORTED assumes an unsupported second element without confirming the corpus doesn't answer it, which the pipeline cannot distinguish from a true miss.",
  "partial-bel-repurchase-and-buyback-pricing":
    "Same pattern: notes say the price-ceiling sub-topic \"were not separately verified\" rather than confirmed absent -- expected set may be incomplete, not a pipeline defect.",
  "partial-kp2-materiality-and-fraud-risk":
    "Notes: fraud-risk indicators \"not verified as separately disclosed\" -- ground truth doesn't establish the second element is genuinely unanswerable from this corpus.",
  "partial-kp2-liability-classification-and-fair-value-hierarchy":
    "Notes: IFRS 13 hierarchy level \"not separately verified as disclosed\" -- same unverified-absence pattern.",
  "repeated-passage-kp2-transitions-both-modification":
    "Expected PARTIALLY_SUPPORTED is built on a single passage the notes call \"relevant to the audit context but does not itself discuss company-registration changes\" -- the question asks specifically about registration changes, which this passage doesn't address at all; the expected minimum-sufficient-evidence-set may simply be wrong/absent rather than partially answerable.",
};

interface AttributionRow {
  caseId: string;
  caseType: string;
  expected: string;
  actual: string;
  candidatePresence: boolean;
  requiredEvidenceRank: number | "";
  selectedFlag: boolean;
  primaryStage: FailureStage;
  secondaryNotes: string;
  groundTruthReviewFlag: boolean;
}

function csvEscape(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

async function main() {
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const companyRepo = new PostgresCompanyRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const provider = new HttpQueryEmbeddingProvider(providerConfig);
  const config = getQaConfig();
  const examinationWindow = config.maxEvidenceSetSize * EXAMINATION_WINDOW_MULTIPLIER;

  const companies = await companyRepo.listCompanies();
  const rows: AttributionRow[] = [];
  const stageCounts = new Map<FailureStage, number>();

  for (const testCase of QA_EVALUATION_DATASET) {
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
    const candidatePassageIds = new Set(candidates.map((c) => c.passageId));

    const baseReranked = createQaReranker(config.secondStageReranker).rerank(testCase.question, candidates, analysis);
    const strategy = getGateStrategyConfig(config);
    const reranked = enrichWithDirectResponsiveness(baseReranked, analysis, strategy, strategy.drivesRanking);
    const rankByPassageId = new Map(reranked.map((c) => [c.passageId, c.relevanceRank]));

    const evidenceSet = buildEvidenceSet(reranked, analysis, config);
    const coherence = checkCoherence(evidenceSet.selected, evidenceSet.rejected, analysis);
    const gateDecision = evaluateGroundedness(evidenceSet, analysis, coherence, config);

    const selectedIds = evidenceSet.selected.map((s) => s.passageId);
    const setProbes = testCase.minimumSufficientEvidenceSets.map((set) =>
      probeSufficientSet(set, candidatePassageIds, rankByPassageId, examinationWindow),
    );
    const recovered = recoveredMinimumSufficientSet(selectedIds, testCase.minimumSufficientEvidenceSets);

    let primaryStage = classifyFailureStage({
      expected: testCase.expectedAnswerability,
      actual: gateDecision.status,
      sufficientSets: testCase.minimumSufficientEvidenceSets,
      setProbes,
      recovered,
    });

    const groundTruthReviewFlag = testCase.id in GROUND_TRUTH_REVIEW_OVERRIDES;
    if (groundTruthReviewFlag && primaryStage !== "PIPELINE_SUCCESS") {
      primaryStage = "GROUND_TRUTH_AMBIGUITY";
    }

    const bestRank = setProbes.map((p) => p.bestRank).filter((r): r is number => r !== null);
    const requiredEvidenceRank = bestRank.length > 0 ? Math.min(...bestRank) : "";

    const secondaryNotes = [
      testCase.minimumSufficientEvidenceSets.length === 0 ? "no-answer-expected case" : `${testCase.minimumSufficientEvidenceSets.length} alternate sufficient set(s)`,
      gateDecision.reasonCodes.length > 0 ? `reasonCodes=${gateDecision.reasonCodes.join("|")}` : "",
      groundTruthReviewFlag ? GROUND_TRUTH_REVIEW_OVERRIDES[testCase.id] : "",
    ]
      .filter(Boolean)
      .join(" -- ");

    rows.push({
      caseId: testCase.id,
      caseType: testCase.caseType,
      expected: testCase.expectedAnswerability,
      actual: gateDecision.status,
      candidatePresence: setProbes.some((p) => p.present),
      requiredEvidenceRank,
      selectedFlag: recovered,
      primaryStage,
      secondaryNotes,
      groundTruthReviewFlag,
    });

    stageCounts.set(primaryStage, (stageCounts.get(primaryStage) ?? 0) + 1);
  }

  const outDir = path.resolve(__dirname, "results");
  mkdirSync(outDir, { recursive: true });
  const header = "case_id,case_type,expected,actual,candidate_presence,required_evidence_rank,selected_flag,primary_stage,secondary_notes,ground_truth_review_flag\n";
  const body = rows
    .map((r) =>
      [
        r.caseId,
        r.caseType,
        r.expected,
        r.actual,
        r.candidatePresence,
        r.requiredEvidenceRank,
        r.selectedFlag,
        r.primaryStage,
        csvEscape(r.secondaryNotes),
        r.groundTruthReviewFlag,
      ].join(","),
    )
    .join("\n");
  const outPath = path.join(outDir, "qa_failure_attribution.csv");
  writeFileSync(outPath, header + body + "\n");

  console.log(`config: reranker=${config.secondStageReranker} maxEvidenceSetSize=${config.maxEvidenceSetSize} examinationWindow=${examinationWindow}`);
  console.log("\n=== Failure stage counts (baseline, n=" + rows.length + ") ===");
  const stages: FailureStage[] = ["RETRIEVAL_MISS", "RERANKING_MISS", "EVIDENCE_SELECTION_MISS", "GATE_MISCLASSIFICATION", "GROUND_TRUTH_AMBIGUITY", "PIPELINE_SUCCESS"];
  for (const stage of stages) {
    console.log(`${stage.padEnd(28)} ${stageCounts.get(stage) ?? 0}`);
  }
  console.log(`\nCSV written to ${outPath}`);

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
