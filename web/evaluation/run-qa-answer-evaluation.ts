/**
 * Milestone 7B.2 `/ask` pipeline evaluation runner. Executes
 * `QA_ANSWER_EVALUATION_DATASET` against the live corpus, the live
 * query-embedding service, and (if `GEMINI_API_KEY` is configured) the
 * real Gemini generation provider. A script (`npx tsx --tsconfig
 * evaluation/tsconfig.json evaluation/run-qa-answer-evaluation.ts`), not a
 * unit test.
 *
 * Per the milestone brief, this characterizes quality -- it is not a
 * pass/fail gate. Metrics reported are exactly what this dataset can
 * honestly support (see `qa-answer-dataset.ts`'s module docstring for why
 * this dataset doesn't carry hand-verified passage-level ground truth the
 * way `qa-dataset.ts` does): retrieval-miss proxy, abstention proxy,
 * answer-status distribution, citation completeness, unsupported-claim
 * proxy (citedEvidence non-empty whenever status is ANSWERED/
 * PARTIALLY_ANSWERED), provider failure rate, and latency percentiles.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { PostgresQaChunkRepository } from "../lib/repositories/postgres-qa-chunk-repository";
import {
  CachingQueryEmbeddingProvider,
  HttpQueryEmbeddingProvider,
  loadHttpQueryEmbeddingProviderConfig,
  queryEmbeddingCacheKeyPrefix,
} from "../lib/services/query-embedding-provider";
import { GeminiGenerationProvider } from "../lib/services/generation/gemini-provider";
import { getGenerationConfig } from "../lib/config/generation-config";
import { retrieveQaEvidence } from "../lib/services/qa/qa-chunk-retrieval-service";
import { generateQaAnswer } from "../lib/services/qa/qa-answer-service";
import { bothSidesPresent, routeQuestion } from "../lib/services/qa/question-router";
import { PostgresCompanyRepository } from "../lib/repositories/postgres-company-repository";
import { closePool } from "../lib/db/pool";
import { meanOf } from "./metrics";
import { QA_ANSWER_EVALUATION_DATASET } from "./qa-answer-dataset";

interface CaseResult {
  id: string;
  caseType: string;
  route: string;
  expectEvidence: boolean;
  evidenceCount: number;
  retrievalMiss: boolean;
  status: string;
  citedCount: number;
  citationCompleteness: number;
  unsupportedClaimSuspected: boolean;
  providerFailed: boolean;
  retrievalLatencyMs: number;
  generationLatencyMs: number | null;
}

async function runCase(
  caseDef: (typeof QA_ANSWER_EVALUATION_DATASET)[number],
  companies: { ticker: string; name: string }[],
): Promise<CaseResult> {
  const embeddingConfig = loadHttpQueryEmbeddingProviderConfig();
  const embeddingProvider = new CachingQueryEmbeddingProvider(
    new HttpQueryEmbeddingProvider(embeddingConfig),
    queryEmbeddingCacheKeyPrefix(embeddingConfig),
  );
  const chunkRepository = new PostgresQaChunkRepository();
  const generationProvider = new GeminiGenerationProvider(getGenerationConfig());

  const decision = routeQuestion(caseDef.question, companies);

  const retrievalStart = Date.now();
  let evidence: Awaited<ReturnType<typeof retrieveQaEvidence>>["evidence"] = [];
  try {
    const result = await retrieveQaEvidence(caseDef.question, embeddingProvider, chunkRepository);
    evidence = result.evidence;
  } catch (error) {
    // A transient embedding-service hiccup on one case must not abort the
    // whole run -- recorded as zero evidence for this case (visible in the
    // CSV as evidence_count=0), never silently skipped.
    console.error(`  [${caseDef.id}] retrieval failed: ${(error as Error).message}`);
  }
  const retrievalLatencyMs = Date.now() - retrievalStart;

  const singleSidedComparisonWarning = decision.route === "COMPARISON_QA" && !bothSidesPresent(evidence);
  const answer = await generateQaAnswer(caseDef.question, evidence, generationProvider, {
    singleSidedComparisonWarning,
  });

  const retrievalMiss = caseDef.expectEvidence && evidence.length === 0;
  const citationCompleteness = answer.citedEvidence.length > 0
    ? answer.citedEvidence.filter((e) => e.citation.label.length > 0).length / answer.citedEvidence.length
    : 1;
  const unsupportedClaimSuspected =
    (answer.status === "ANSWERED" || answer.status === "PARTIALLY_ANSWERED") && answer.citedEvidence.length === 0;

  return {
    id: caseDef.id,
    caseType: caseDef.caseType,
    route: decision.route,
    expectEvidence: caseDef.expectEvidence,
    evidenceCount: evidence.length,
    retrievalMiss,
    status: answer.status,
    citedCount: answer.citedEvidence.length,
    citationCompleteness,
    unsupportedClaimSuspected,
    providerFailed: answer.status === "PROVIDER_UNAVAILABLE",
    retrievalLatencyMs,
    generationLatencyMs: answer.providerLatencyMs,
  };
}

function percentile(values: readonly number[], p: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[index];
}

function toCsv(rows: CaseResult[]): string {
  const header = [
    "id",
    "case_type",
    "route",
    "expect_evidence",
    "evidence_count",
    "retrieval_miss",
    "status",
    "cited_count",
    "citation_completeness",
    "unsupported_claim_suspected",
    "provider_failed",
    "retrieval_latency_ms",
    "generation_latency_ms",
  ];
  const lines = rows.map((r) =>
    [
      r.id,
      r.caseType,
      r.route,
      r.expectEvidence,
      r.evidenceCount,
      r.retrievalMiss,
      r.status,
      r.citedCount,
      r.citationCompleteness.toFixed(2),
      r.unsupportedClaimSuspected,
      r.providerFailed,
      r.retrievalLatencyMs,
      r.generationLatencyMs ?? "",
    ].join(","),
  );
  return [header.join(","), ...lines].join("\n") + "\n";
}

async function main() {
  const companyRepository = new PostgresCompanyRepository();
  const companies = (await companyRepository.listCompanies()).map((c) => ({ ticker: c.ticker, name: c.name }));

  const results: CaseResult[] = [];
  for (const caseDef of QA_ANSWER_EVALUATION_DATASET) {
    const result = await runCase(caseDef, companies);
    results.push(result);
    console.log(`[${result.status}] ${caseDef.id} -- route=${result.route} evidence=${result.evidenceCount}`);
  }

  const noAnswerCases = results.filter((r) => !r.expectEvidence);
  const answerableCases = results.filter((r) => r.expectEvidence);
  const retrievalMissRate = answerableCases.length > 0
    ? answerableCases.filter((r) => r.retrievalMiss).length / answerableCases.length
    : 0;
  const correctAbstentionRate = noAnswerCases.length > 0
    ? noAnswerCases.filter((r) => r.evidenceCount === 0 || r.status === "INSUFFICIENT_EVIDENCE").length / noAnswerCases.length
    : 0;
  const providerFailureRate = results.filter((r) => r.providerFailed).length / results.length;
  const unsupportedClaimRate = results.filter((r) => r.unsupportedClaimSuspected).length / results.length;
  const citationCompleteness = meanOf(results.map((r) => r.citationCompleteness));
  const retrievalLatencies = results.map((r) => r.retrievalLatencyMs);
  const totalLatencies = results.map((r) => r.retrievalLatencyMs + (r.generationLatencyMs ?? 0));

  console.log("\n=== Summary ===");
  console.log(`Cases: ${results.length}`);
  console.log(`Retrieval-miss rate (answerable cases): ${(retrievalMissRate * 100).toFixed(1)}%`);
  console.log(`Correct-abstention rate (no-answer cases): ${(correctAbstentionRate * 100).toFixed(1)}%`);
  console.log(`Provider-failure rate: ${(providerFailureRate * 100).toFixed(1)}%`);
  console.log(`Unsupported-claim-suspected rate: ${(unsupportedClaimRate * 100).toFixed(1)}%`);
  console.log(`Citation completeness (mean): ${citationCompleteness.toFixed(2)}`);
  console.log(`Retrieval latency p50/p95: ${percentile(retrievalLatencies, 50)}ms / ${percentile(retrievalLatencies, 95)}ms`);
  console.log(`End-to-end latency p50/p95: ${percentile(totalLatencies, 50)}ms / ${percentile(totalLatencies, 95)}ms`);
  if (providerFailureRate > 0) {
    console.log(
      "\nNote: PROVIDER_UNAVAILABLE cases reflect no GEMINI_API_KEY (or a provider error) during this run -- " +
        "answer-quality metrics (numeric correctness, comparison-direction correctness, abstention accuracy on " +
        "generated text) cannot be assessed without a real generated answer. Retrieval-side metrics above remain valid.",
    );
  }

  const outDir = path.resolve(__dirname, "results");
  mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, "qa_answer_evaluation.csv");
  writeFileSync(outPath, toCsv(results));
  console.log(`\nWrote ${outPath}`);

  await closePool();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
