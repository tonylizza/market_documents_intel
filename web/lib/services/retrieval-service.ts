import "server-only";
import type { PassageSearchParams } from "@/lib/domain/passage";
import type {
  GroupedRetrievalResult,
  RetrievalContext,
  RetrievalMode,
  RetrievalPage,
  RetrievalResult,
} from "@/lib/domain/retrieval";
import type { SemanticRetrievalRepository } from "@/lib/repositories/semantic-retrieval-repository";
import type { QueryEmbeddingProvider } from "@/lib/services/query-embedding-provider";
import { QueryEmbeddingProviderError } from "@/lib/services/query-embedding-provider";
import { getRetrievalConfig } from "@/lib/config/retrieval-config";
import { reciprocalRankFusion, type RankedItem } from "@/lib/services/rrf";
import { formatCitationLabel } from "@/lib/services/citation";
import { buildExcerpt, buildHighlightSpans, extractHighlightTerms } from "@/lib/services/passage-highlight";
import { QualityAdjustedSemanticReranker, type SemanticReranker } from "@/lib/services/semantic-reranker";
import type { QualityExplanationCode } from "@/lib/services/passage-quality";
import { query } from "@/lib/db/pool";

function getSemanticReranker(): SemanticReranker {
  const config = getRetrievalConfig();
  return new QualityAdjustedSemanticReranker({
    headingOnlyFragmentFactor: config.headingOnlyFragmentFactor,
    genericHeadingFactor: config.genericHeadingFactor,
    lowSubstantiveFactor: config.lowSubstantiveFactor,
  });
}

const CONFIDENCE_RANK: Record<string, number> = { HIGH: 0, MEDIUM: 1, LOW: 2, NEEDS_REVIEW: 3 };

/** Resolves the currently active publication id via the one view every
 * `app_readonly` grant already exposes -- the sanctioned pattern documented
 * in `scripts/sql/app_roles.sql` for reading the active publication id
 * without any dedicated grant on `app_internal`. */
async function getActivePublicationId(): Promise<string | null> {
  const rows = await query<{ publication_id: string }>(`SELECT publication_id FROM app.current_companies LIMIT 1`);
  return rows[0]?.publication_id ?? null;
}

function evidenceUrlFor(context: RetrievalContext): string {
  if (context.passageComparisonId) return `/passages/${context.passageComparisonId}`;
  return `/companies/${context.companyTicker}`;
}

/** Chooses one "best" context to lead a group when a passage expands into
 * more than one valid context: prefers higher confidence, then the later
 * report side (more current), then a stable id tie-break. Never discards
 * the others -- they're preserved as `additionalContexts`. */
function sortContextsForGrouping(contexts: RetrievalContext[]): RetrievalContext[] {
  return [...contexts].sort((a, b) => {
    const confidenceDiff = (CONFIDENCE_RANK[a.confidence ?? "NEEDS_REVIEW"] ?? 9) - (CONFIDENCE_RANK[b.confidence ?? "NEEDS_REVIEW"] ?? 9);
    if (confidenceDiff !== 0) return confidenceDiff;
    if (a.reportSide !== b.reportSide) return a.reportSide === "LATER" ? -1 : 1;
    return a.contextId.localeCompare(b.contextId);
  });
}

interface BuildResultInput {
  passageId: string;
  contexts: RetrievalContext[];
  rank: number;
  /** Raw cosine similarity -- always the un-adjusted value; weak-match
   * strength is judged against this, never the adjusted score. */
  semanticSimilarity: number | null;
  qualityFactor: number | null;
  adjustedSemanticScore: number | null;
  qualityExplanationCode: QualityExplanationCode | null;
  semanticRawRank: number | null;
  semanticAdjustedRank: number | null;
  lexicalRankPosition: number | null;
  fusedScore: number | null;
  mode: RetrievalMode;
  vectorSearchMode: "exact" | "hnsw" | null;
  model: string | null;
  modelRevision: string | null;
  queryTerms: readonly string[];
  contextsPerPassageCap: number;
  minimumSemanticSimilarity: number;
  publicationId: string | null;
}

function buildGroupedResult(input: BuildResultInput): GroupedRetrievalResult | null {
  if (input.contexts.length === 0) return null;
  const ordered = sortContextsForGrouping(input.contexts);
  const primary = ordered[0];
  const additionalContexts = ordered.slice(1, input.contextsPerPassageCap);

  const strength =
    input.semanticSimilarity !== null
      ? input.semanticSimilarity >= input.minimumSemanticSimilarity
        ? "strong"
        : "weak"
      : null;

  const citation = {
    publicationId: input.publicationId ?? "",
    retrievalContextId: primary.contextId,
    passageId: primary.passageId,
    passageComparisonId: primary.passageComparisonId,
    reportComparisonId: primary.reportComparisonId,
    reportSide: primary.reportSide,
    reportId: primary.reportId,
    firstPageNumber: primary.firstPageNumber,
    lastPageNumber: primary.lastPageNumber,
    label: formatCitationLabel(primary),
  };

  const excerpt = buildExcerpt(primary.text, input.queryTerms);
  const headingHighlight = primary.heading ? buildHighlightSpans(primary.heading, input.queryTerms) : null;
  const evidenceUrl = evidenceUrlFor(primary);

  const result: RetrievalResult = {
    context: primary,
    additionalContexts,
    excerpt,
    headingHighlight,
    citation,
    diagnostics: {
      mode: input.mode,
      vectorSearchMode: input.vectorSearchMode,
      semanticSimilarity: input.semanticSimilarity,
      qualityFactor: input.qualityFactor,
      adjustedSemanticScore: input.adjustedSemanticScore,
      qualityExplanationCode: input.qualityExplanationCode,
      semanticRawRank: input.semanticRawRank,
      semanticAdjustedRank: input.semanticAdjustedRank,
      lexicalRankPosition: input.lexicalRankPosition,
      fusedScore: input.fusedScore,
      model: input.model,
      modelRevision: input.modelRevision,
      strength,
    },
    evidenceUrl,
    passageDetailUrl: primary.passageComparisonId ? `/passages/${primary.passageComparisonId}` : null,
    finalRank: input.rank,
  };
  return { ...result, hasAdditionalContexts: additionalContexts.length > 0 };
}

export async function searchSemantic(
  repository: SemanticRetrievalRepository,
  embeddingProvider: QueryEmbeddingProvider,
  params: PassageSearchParams,
  maxResults: number,
): Promise<RetrievalPage> {
  const config = getRetrievalConfig();
  if (!params.query) {
    return { results: [], mode: "semantic", weakMatchNotice: false, providerUnavailable: false };
  }

  let embedding;
  try {
    embedding = await embeddingProvider.embedQuery(params.query);
  } catch (error) {
    if (error instanceof QueryEmbeddingProviderError) {
      console.error("Query-embedding provider failed, semantic search unavailable:", error.message);
      return { results: [], mode: "semantic", weakMatchNotice: false, providerUnavailable: true };
    }
    throw error;
  }

  const effectiveMode = await repository.resolveVectorSearchMode(config.vectorSearchMode);
  const candidates = await repository.searchSemanticCandidates(
    embedding.vector,
    params,
    config.semanticCandidateLimit,
    effectiveMode,
  );
  if (candidates.length === 0) {
    return { results: [], mode: "semantic", weakMatchNotice: false, providerUnavailable: false };
  }

  // Milestone 7B.1a: rerank the bounded candidate set to counter
  // short-passage similarity inflation -- raw similarity/rank are preserved
  // separately from the adjusted score/rank (see `semantic-reranker.ts`).
  const reranked = getSemanticReranker().rerank(params.query, candidates);
  const rawSimilarityByPassage = new Map(candidates.map((c) => [c.passageId, c.similarity]));

  const contexts = await repository.expandRetrievalContexts(candidates.map((c) => c.passageId), params);
  const contextsByPassage = new Map<string, RetrievalContext[]>();
  for (const ctx of contexts) {
    const list = contextsByPassage.get(ctx.passageId) ?? [];
    list.push(ctx);
    contextsByPassage.set(ctx.passageId, list);
  }

  const queryTerms = extractHighlightTerms(params.query);
  const publicationId = await getActivePublicationId();

  const results: GroupedRetrievalResult[] = [];
  let rank = 0;
  for (const candidate of reranked) {
    const passageContexts = contextsByPassage.get(candidate.passageId);
    if (!passageContexts || passageContexts.length === 0) continue;
    rank += 1;
    const grouped = buildGroupedResult({
      passageId: candidate.passageId,
      contexts: passageContexts,
      rank,
      semanticSimilarity: rawSimilarityByPassage.get(candidate.passageId) ?? candidate.rawSimilarity,
      qualityFactor: candidate.qualityFactor,
      adjustedSemanticScore: candidate.adjustedScore,
      qualityExplanationCode: candidate.explanationCode,
      semanticRawRank: candidate.originalRank,
      semanticAdjustedRank: candidate.finalRank,
      lexicalRankPosition: null,
      fusedScore: null,
      mode: "semantic",
      vectorSearchMode: effectiveMode,
      model: embedding.model,
      modelRevision: embedding.modelRevision,
      queryTerms,
      contextsPerPassageCap: config.contextsPerPassageCap,
      minimumSemanticSimilarity: config.minimumSemanticSimilarity,
      publicationId,
    });
    if (grouped) results.push(grouped);
    if (results.length >= maxResults) break;
  }

  const weakMatchNotice = results.length > 0 && results.every((r) => r.diagnostics.strength === "weak");
  return { results, mode: "semantic", weakMatchNotice, providerUnavailable: false };
}

export async function searchHybrid(
  repository: SemanticRetrievalRepository,
  embeddingProvider: QueryEmbeddingProvider,
  params: PassageSearchParams,
  maxResults: number,
): Promise<RetrievalPage> {
  const config = getRetrievalConfig();
  if (!params.query) {
    return { results: [], mode: "hybrid", weakMatchNotice: false, providerUnavailable: false };
  }

  const lexicalCandidates = await repository.searchLexicalCandidates(params, config.lexicalCandidateLimit);

  let embedding;
  try {
    embedding = await embeddingProvider.embedQuery(params.query);
  } catch (error) {
    if (error instanceof QueryEmbeddingProviderError) {
      // Semantic component unavailable -- hybrid degrades to lexical-only
      // fusion rather than failing the whole search (a partial, honestly
      // labeled result beats an outage-shaped error for a filter-driven
      // corpus search).
      console.error("Query-embedding provider failed, hybrid search degrading to lexical-only:", error.message);
      return searchHybridLexicalOnly(repository, params, maxResults, lexicalCandidates);
    }
    throw error;
  }

  const effectiveMode = await repository.resolveVectorSearchMode(config.vectorSearchMode);
  const semanticCandidates = await repository.searchSemanticCandidates(
    embedding.vector,
    params,
    config.semanticCandidateLimit,
    effectiveMode,
  );

  // Milestone 7B.1a: RRF fuses on the quality-*adjusted* semantic rank, not
  // raw cosine rank -- a short-fragment candidate with high raw similarity
  // but a demoted adjusted rank must not get an inflated fused position
  // either (milestone requirement: "Apply RRF using the selected semantic
  // rank, not necessarily raw cosine rank").
  const rerankedSemantic = getSemanticReranker().rerank(params.query, semanticCandidates);
  const rawSimilarityByPassage = new Map(semanticCandidates.map((c) => [c.passageId, c.similarity]));
  const rerankedByPassage = new Map(rerankedSemantic.map((c) => [c.passageId, c]));

  const lexicalRanking: RankedItem[] = lexicalCandidates.map((c) => ({ id: c.passageId, rankPosition: c.rankPosition }));
  const semanticRanking: RankedItem[] = rerankedSemantic.map((c) => ({ id: c.passageId, rankPosition: c.finalRank }));
  const fused = reciprocalRankFusion(lexicalRanking, semanticRanking, config.rrfK);

  const candidateIds = fused.slice(0, config.semanticCandidateLimit * config.contextExpansionMultiplier).map((f) => f.id);
  const contexts = await repository.expandRetrievalContexts(candidateIds, params);
  const contextsByPassage = new Map<string, RetrievalContext[]>();
  for (const ctx of contexts) {
    const list = contextsByPassage.get(ctx.passageId) ?? [];
    list.push(ctx);
    contextsByPassage.set(ctx.passageId, list);
  }

  const queryTerms = extractHighlightTerms(params.query);
  const publicationId = await getActivePublicationId();

  const results: GroupedRetrievalResult[] = [];
  let rank = 0;
  for (const item of fused) {
    const passageContexts = contextsByPassage.get(item.id);
    if (!passageContexts || passageContexts.length === 0) continue;
    rank += 1;
    const semanticEntry = rerankedByPassage.get(item.id);
    const grouped = buildGroupedResult({
      passageId: item.id,
      contexts: passageContexts,
      rank,
      semanticSimilarity: rawSimilarityByPassage.get(item.id) ?? null,
      qualityFactor: semanticEntry?.qualityFactor ?? null,
      adjustedSemanticScore: semanticEntry?.adjustedScore ?? null,
      qualityExplanationCode: semanticEntry?.explanationCode ?? null,
      semanticRawRank: semanticEntry?.originalRank ?? null,
      semanticAdjustedRank: semanticEntry?.finalRank ?? null,
      lexicalRankPosition: item.lexicalRankPosition,
      fusedScore: item.fusedScore,
      mode: "hybrid",
      vectorSearchMode: effectiveMode,
      model: embedding.model,
      modelRevision: embedding.modelRevision,
      queryTerms,
      contextsPerPassageCap: config.contextsPerPassageCap,
      minimumSemanticSimilarity: config.minimumSemanticSimilarity,
      publicationId,
    });
    if (grouped) results.push(grouped);
    if (results.length >= maxResults) break;
  }

  return { results, mode: "hybrid", weakMatchNotice: false, providerUnavailable: false };
}

async function searchHybridLexicalOnly(
  repository: SemanticRetrievalRepository,
  params: PassageSearchParams,
  maxResults: number,
  lexicalCandidates: Awaited<ReturnType<SemanticRetrievalRepository["searchLexicalCandidates"]>>,
): Promise<RetrievalPage> {
  if (lexicalCandidates.length === 0) {
    return { results: [], mode: "hybrid", weakMatchNotice: false, providerUnavailable: true };
  }
  const contexts = await repository.expandRetrievalContexts(
    lexicalCandidates.map((c) => c.passageId),
    params,
  );
  const contextsByPassage = new Map<string, RetrievalContext[]>();
  for (const ctx of contexts) {
    const list = contextsByPassage.get(ctx.passageId) ?? [];
    list.push(ctx);
    contextsByPassage.set(ctx.passageId, list);
  }
  const queryTerms = params.query ? extractHighlightTerms(params.query) : [];
  const publicationId = await getActivePublicationId();
  const config = getRetrievalConfig();

  const results: GroupedRetrievalResult[] = [];
  let rank = 0;
  for (const candidate of lexicalCandidates) {
    const passageContexts = contextsByPassage.get(candidate.passageId);
    if (!passageContexts || passageContexts.length === 0) continue;
    rank += 1;
    const grouped = buildGroupedResult({
      passageId: candidate.passageId,
      contexts: passageContexts,
      rank,
      semanticSimilarity: null,
      qualityFactor: null,
      adjustedSemanticScore: null,
      qualityExplanationCode: null,
      semanticRawRank: null,
      semanticAdjustedRank: null,
      lexicalRankPosition: candidate.rankPosition,
      fusedScore: null,
      mode: "hybrid",
      vectorSearchMode: null,
      model: null,
      modelRevision: null,
      queryTerms,
      contextsPerPassageCap: config.contextsPerPassageCap,
      minimumSemanticSimilarity: config.minimumSemanticSimilarity,
      publicationId,
    });
    if (grouped) results.push(grouped);
    if (results.length >= maxResults) break;
  }
  return { results, mode: "hybrid", weakMatchNotice: false, providerUnavailable: true };
}
