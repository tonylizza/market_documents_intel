import "server-only";
import { PostgresSemanticRetrievalRepository } from "@/lib/repositories/postgres-semantic-retrieval-repository";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import { CachingQueryEmbeddingProvider, HttpQueryEmbeddingProvider, queryEmbeddingCacheKeyPrefix, loadHttpQueryEmbeddingProviderConfig } from "@/lib/services/query-embedding-provider";
import { QueryEmbeddingProviderError } from "@/lib/services/query-embedding-provider";
import { parsePassageSearchParams } from "@/lib/services/passage-search-params";
import { analyzeQuestion } from "@/lib/services/qa/query-analysis";
import { generateCandidates } from "@/lib/services/qa/candidate-generation";
import { createQaReranker } from "@/lib/services/qa/qa-reranker";
import { buildEvidenceSet } from "@/lib/services/qa/evidence-set-builder";
import { checkCoherence } from "@/lib/services/qa/coherence-checker";
import { evaluateGroundedness } from "@/lib/services/qa/groundedness-gate";
import { buildEvidencePackage } from "@/lib/services/qa/evidence-package";
import { enrichWithDirectResponsiveness } from "@/lib/services/qa/direct-responsiveness";
import { getQaConfig, getGateStrategyConfig } from "@/lib/config/qa-config";
import { query } from "@/lib/db/pool";
import type { EvidencePackage, RerankedEvidenceCandidate } from "@/lib/domain/qa-evidence";

/**
 * Milestone 7B.1b: single server-side orchestration entry point for the
 * Q&A evidence-selection pipeline -- the only place `/evidence-review`
 * calls into. Wires query analysis -> candidate generation -> reranking ->
 * evidence-set construction -> coherence -> groundedness gate ->
 * evidence-package assembly, using exactly the same repository methods and
 * config as the evaluation runner (`evaluation/run-qa-evaluation.ts`), so
 * production behavior and evaluation behavior never drift.
 */

async function getActivePublicationId(): Promise<string | null> {
  const rows = await query<{ publication_id: string }>(`SELECT publication_id FROM app.current_companies LIMIT 1`);
  return rows[0]?.publication_id ?? null;
}

export interface EvidencePipelineResult {
  evidencePackage: EvidencePackage;
  candidates: readonly RerankedEvidenceCandidate[];
}

export async function runEvidencePipeline(question: string): Promise<EvidencePipelineResult> {
  const totalStart = Date.now();
  const companyRepo = new PostgresCompanyRepository();
  const semanticRepo = new PostgresSemanticRetrievalRepository();
  const config = getQaConfig();

  const analysisStart = Date.now();
  const companies = await companyRepo.listCompanies();
  const analysis = analyzeQuestion(question, companies);
  const analysisLatency = Date.now() - analysisStart;

  const params = parsePassageSearchParams({
    q: analysis.normalizedQuestion,
    company: analysis.requiredTicker ?? undefined,
    periodStart: analysis.dateRange?.start ?? undefined,
    periodEnd: analysis.dateRange?.end ?? undefined,
    category: analysis.requiredCategory ?? undefined,
  });

  const embeddingStart = Date.now();
  let embedding = null;
  try {
    // Config loading (throws `QueryEmbeddingProviderError` synchronously
    // when `QUERY_EMBEDDING_SERVICE_URL` is unset) is deliberately inside
    // this same try/catch as the network call -- a missing/misconfigured
    // embedding service must degrade to keyword-only candidate generation,
    // never fail the whole request (milestone: "provider failure degrades
    // safely to deterministic baseline").
    const providerConfig = loadHttpQueryEmbeddingProviderConfig();
    const embeddingProvider = new CachingQueryEmbeddingProvider(
      new HttpQueryEmbeddingProvider(providerConfig),
      queryEmbeddingCacheKeyPrefix(providerConfig),
    );
    embedding = await embeddingProvider.embedQuery(question);
  } catch (error) {
    if (!(error instanceof QueryEmbeddingProviderError)) throw error;
    // Degrades safely to keyword-only candidate generation -- never fails
    // the whole request just because the embedding service is unavailable.
  }

  const [publicationId, candidates] = await Promise.all([
    getActivePublicationId(),
    generateCandidates(semanticRepo, question, embedding, params, config, null),
  ]);
  const candidateLatency = Date.now() - embeddingStart;

  const rerankStart = Date.now();
  const baseReranked = createQaReranker(config.secondStageReranker).rerank(question, candidates, analysis);
  const strategy = getGateStrategyConfig(config);
  const reranked = enrichWithDirectResponsiveness(baseReranked, analysis, strategy, strategy.drivesRanking);
  const rerankLatency = Date.now() - rerankStart;

  const evidenceSetStart = Date.now();
  const evidenceSet = buildEvidenceSet(reranked, analysis, config);
  const evidenceSetLatency = Date.now() - evidenceSetStart;

  const coherence = checkCoherence(evidenceSet.selected, evidenceSet.rejected, analysis);

  const gateStart = Date.now();
  const gateDecision = evaluateGroundedness(evidenceSet, analysis, coherence, config);
  const gateLatency = Date.now() - gateStart;

  const evidencePackage = buildEvidencePackage({
    publicationId,
    question,
    analysis,
    gateDecision,
    evidenceSet,
    coherence,
    candidateCount: candidates.length,
    candidateSources: [...new Set(candidates.flatMap((c) => c.sources))],
    retrievalMode: embedding ? "hybrid" : "keyword",
    rerankerMethod: config.secondStageReranker,
    latencyMs: {
      queryAnalysis: analysisLatency,
      candidateGeneration: candidateLatency,
      reranking: rerankLatency,
      evidenceSetConstruction: evidenceSetLatency,
      groundednessGate: gateLatency,
      total: Date.now() - totalStart,
    },
  });

  return { evidencePackage, candidates: reranked };
}
