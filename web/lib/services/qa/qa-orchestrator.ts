import "server-only";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import { PostgresQaChunkRepository } from "@/lib/repositories/postgres-qa-chunk-repository";
import {
  CachingQueryEmbeddingProvider,
  HttpQueryEmbeddingProvider,
  QueryEmbeddingProviderError,
  loadHttpQueryEmbeddingProviderConfig,
  queryEmbeddingCacheKeyPrefix,
} from "@/lib/services/query-embedding-provider";
import { GeminiGenerationProvider } from "@/lib/services/generation/gemini-provider";
import { getGenerationConfig } from "@/lib/config/generation-config";
import { retrieveQaEvidence } from "@/lib/services/qa/qa-chunk-retrieval-service";
import { generateQaAnswer } from "@/lib/services/qa/qa-answer-service";
import { bothSidesPresent, groupEvidenceByCompanyAndReport, routeQuestion, type QaRoute } from "@/lib/services/qa/question-router";
import type { QaAnswer } from "@/lib/domain/qa-answer";
import type { QueryAnalysis } from "@/lib/domain/qa-evidence";

export interface QaFilters {
  companyTicker: string | null;
  /** Optional report/year filter (brief: "optional report/year filter") --
   * matched against the citation's report period-end year rather than a
   * specific report id, so the filter works as a plain `<select>` of
   * observed years without a second, company-dependent report dropdown. */
  reportYear: string | null;
}

export interface QaPipelineResult {
  route: QaRoute;
  analysis: QueryAnalysis;
  answer: QaAnswer;
  comparisonLinkTicker: string | null;
  grouped: ReturnType<typeof groupEvidenceByCompanyAndReport>;
  retrievalLatencyMs: number;
  totalLatencyMs: number;
}

/**
 * Milestone 7B.2 single server-side orchestration entry point for `/ask` --
 * mirrors `qa-pipeline.ts::runEvidencePipeline`'s "the only place the route
 * calls into" discipline, but wires the NEW standard-RAG chunk retrieval +
 * generation stack (`qa-chunk-retrieval-service.ts` / `qa-answer-
 * service.ts`), entirely separate from the canonical-passage evidence
 * pipeline `/evidence-review` uses. Never mutates or reads from
 * `qa_experiment`.
 */
export async function runQaPipeline(questionText: string, filters: QaFilters = { companyTicker: null, reportYear: null }): Promise<QaPipelineResult> {
  const totalStart = Date.now();

  const companyRepository = new PostgresCompanyRepository();
  const companies = await companyRepository.listCompanies();
  const decision = routeQuestion(questionText, companies);

  const embeddingConfig = loadHttpQueryEmbeddingProviderConfig();
  const embeddingProvider = new CachingQueryEmbeddingProvider(
    new HttpQueryEmbeddingProvider(embeddingConfig),
    queryEmbeddingCacheKeyPrefix(embeddingConfig),
  );

  const chunkRepository = new PostgresQaChunkRepository();

  // DOCUMENT_QA/COMPARISON_QA (brief: "standard chunk retrieval within the
  // selected reports") scope to the single company `analyzeQuestion`
  // detected in the question text, even when the user didn't also pick it
  // from the `/ask` company filter -- CORPUS_QA is deliberately never
  // auto-scoped this way, it's the "broad/cross-company" route by
  // definition. An explicit UI filter always takes precedence over the
  // detected ticker. Applied at the SQL level inside `retrieveQaEvidence`
  // (never as a post-hoc filter on an already-fetched, company-agnostic
  // top-K -- that would wrongly zero out a company whose chunks didn't
  // happen to rank in the unfiltered top-K, confirmed by a live /ask smoke
  // test before this fix).
  const effectiveCompanyTicker =
    filters.companyTicker ??
    (decision.route !== "CORPUS_QA" && decision.analysis.tickers.length === 1 ? decision.analysis.tickers[0] : null);

  const retrievalStart = Date.now();
  let evidence: Awaited<ReturnType<typeof retrieveQaEvidence>>["evidence"] = [];
  try {
    const result = await retrieveQaEvidence(
      questionText,
      embeddingProvider,
      chunkRepository,
      undefined,
      effectiveCompanyTicker,
    );
    evidence = result.evidence;
  } catch (error) {
    if (!(error instanceof QueryEmbeddingProviderError)) throw error;
    // Query-embedding service unavailable -- fall through with zero
    // evidence, which `generateQaAnswer` turns into INSUFFICIENT_EVIDENCE
    // rather than crashing the page.
    evidence = [];
  }
  const retrievalLatencyMs = Date.now() - retrievalStart;

  // Report-year filtering stays post-hoc: it doesn't scope the ANN search
  // the way company does (year isn't part of the top-K selection problem
  // the same way), and it only ever narrows an already company-correct
  // result set.
  const filteredEvidence = evidence.filter((e) => {
    if (filters.reportYear && e.citation.reportPeriodEnd?.slice(0, 4) !== filters.reportYear) return false;
    return true;
  });

  const generationProvider = new GeminiGenerationProvider(getGenerationConfig());
  const singleSidedComparisonWarning = decision.route === "COMPARISON_QA" && !bothSidesPresent(filteredEvidence);
  const answer = await generateQaAnswer(questionText, filteredEvidence, generationProvider, {
    singleSidedComparisonWarning,
  });

  const grouped = decision.route === "CORPUS_QA" ? groupEvidenceByCompanyAndReport(answer.allEvidence) : [];

  return {
    route: decision.route,
    analysis: decision.analysis,
    answer,
    comparisonLinkTicker: decision.comparisonLinkTicker,
    grouped,
    retrievalLatencyMs,
    totalLatencyMs: Date.now() - totalStart,
  };
}
