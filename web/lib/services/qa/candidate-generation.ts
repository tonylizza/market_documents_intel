import "server-only";
import type { PassageSearchParams } from "@/lib/domain/passage";
import type { QueryEmbedding } from "@/lib/domain/retrieval";
import type { EvidenceCandidate, EvidenceCandidateSource } from "@/lib/domain/qa-evidence";
import type { SemanticRetrievalRepository } from "@/lib/repositories/semantic-retrieval-repository";
import { QualityAdjustedSemanticReranker, type SemanticReranker } from "@/lib/services/semantic-reranker";
import { getRetrievalConfig } from "@/lib/config/retrieval-config";
import { formatCitationLabel } from "@/lib/services/citation";
import { reciprocalRankFusion } from "@/lib/services/rrf";
import { extractConceptTerms, STOPWORDS } from "@/lib/services/qa/qa-reranker";
import type { QaConfig } from "@/lib/config/qa-config";
import type { QaChunkRetrievalRepository } from "@/lib/repositories/qa-chunk-retrieval-repository";
import { mapChunkHitsToParents, type ChunkParentCandidate } from "@/lib/services/qa/qa-chunk-fusion";

/**
 * Milestone 7B.1b: Q&A-specific candidate generation. Reuses the existing
 * `SemanticRetrievalRepository` methods that already power `/passages`
 * (`searchLexicalCandidates`, `searchSemanticCandidates`,
 * `expandRetrievalContexts`) -- no new SQL, and this never replaces or
 * modifies the public `/passages` ranking (`retrieval-service.ts` is
 * untouched). Bounded by `QaConfig.candidateLimitPerSource` on each source
 * independently (never the full corpus) -- see milestone: "do not send all
 * 21,962 vectors ... into application memory".
 *
 * Duplicates the tiny `QualityAdjustedSemanticReranker` factory already
 * private to `retrieval-service.ts` rather than exporting/importing it --
 * deliberately keeps the shipped `/passages` retrieval service file
 * untouched by this milestone.
 */
function getSemanticReranker(): SemanticReranker {
  const config = getRetrievalConfig();
  return new QualityAdjustedSemanticReranker({
    headingOnlyFragmentFactor: config.headingOnlyFragmentFactor,
    genericHeadingFactor: config.genericHeadingFactor,
    lowSubstantiveFactor: config.lowSubstantiveFactor,
  });
}

/** Milestone 7B.1c Phase 1 finding: `searchLexicalCandidates` passes its
 * `query` straight into `websearch_to_tsquery`, which ANDs every content
 * word by default -- appropriate for `/passages`' short, intentional
 * search-box queries, but disastrous for a full question sentence (a
 * 6-content-word question requires all 6 to appear verbatim in one
 * passage, which real prose almost never does; live-corpus verification
 * during Phase 1 attribution found this produced *zero* lexical candidates
 * for several genuinely-answerable single-passage questions). Rebuilt here
 * as an OR of the question's significant terms -- same shared SQL/ranking
 * function, same stopword list as the reranker's concept-coverage scoring
 * (`extractConceptTerms`), just a looser query shape. The company
 * ticker/name is excluded from the term set since `params.company` already
 * scopes the search -- without this, a ticker like "ACT" collides with the
 * common English word "act" in unrelated passages and dilutes ts_rank. */
function buildLexicalQuery(question: string, companyTicker: string | null): string {
  const terms = extractConceptTerms(question).filter((term) => term !== companyTicker?.toLowerCase() && !STOPWORDS.has(term));
  return terms.length > 0 ? terms.join(" OR ") : question;
}

/** Milestone 7B.1c Phase 1 finding: `searchLexicalCandidates`'s SQL joins
 * each passage to every report-comparison it participates in before
 * applying `LIMIT`, so a passage appearing in 2 comparisons consumes 2 rows
 * of the requested budget -- live-corpus verification found this roughly
 * halves the number of *distinct* passages actually returned. Requesting a
 * larger raw row limit here (purely a QA-local call-site parameter, not a
 * change to the shared SQL) absorbs that fan-out; the existing
 * `lexicalByPassage` map below already collapses to one entry per passage. */
const LEXICAL_FANOUT_LIMIT_MULTIPLIER = 4;

/** Milestone 7B.1d (experimental): opt-in chunk-retrieval candidate source.
 * `undefined`/omitted preserves `generateCandidates`'s exact pre-7B.1d
 * behavior (no `qa_experiment` query, no new candidates, no regression risk
 * to the shipped default pipeline or public search) -- only evaluation
 * scripts comparing chunk strategies pass this. */
export interface ChunkCandidateOptions {
  repo: QaChunkRetrievalRepository;
  strategies?: readonly string[] | null;
  childLimit: number;
}

export async function generateCandidates(
  repo: SemanticRetrievalRepository,
  question: string,
  embedding: QueryEmbedding | null,
  params: PassageSearchParams,
  config: QaConfig,
  publicationId: string | null,
  chunkOptions?: ChunkCandidateOptions,
): Promise<EvidenceCandidate[]> {
  const lexicalParams: PassageSearchParams = { ...params, query: buildLexicalQuery(question, params.company) };
  const lexicalCandidates = await repo.searchLexicalCandidates(lexicalParams, config.candidateLimitPerSource * LEXICAL_FANOUT_LIMIT_MULTIPLIER);
  const semanticCandidates = embedding
    ? await repo.searchSemanticCandidates(embedding.vector, params, config.candidateLimitPerSource, "auto")
    : [];
  const reranked = getSemanticReranker().rerank(question, semanticCandidates);

  const lexicalByPassage = new Map(lexicalCandidates.map((c) => [c.passageId, c]));
  const semanticByPassage = new Map(reranked.map((c) => [c.passageId, c]));

  const rrfFused = reciprocalRankFusion(
    lexicalCandidates.map((c) => ({ id: c.passageId, rankPosition: c.rankPosition })),
    reranked.map((c) => ({ id: c.passageId, rankPosition: c.finalRank })),
    getRetrievalConfig().rrfK,
  );
  const rrfRankByPassage = new Map(rrfFused.map((item, index) => [item.id, index + 1]));

  const chunkParents: Map<string, ChunkParentCandidate> =
    embedding && chunkOptions
      ? mapChunkHitsToParents(
          await chunkOptions.repo.searchChunkCandidates(embedding.vector, chunkOptions.childLimit, chunkOptions.strategies ?? null),
        )
      : new Map();

  const passageIds = [...new Set([...lexicalByPassage.keys(), ...semanticByPassage.keys(), ...chunkParents.keys()])];
  if (passageIds.length === 0) return [];

  const contexts = await repo.expandRetrievalContexts(passageIds, params);

  // Milestone 7B.1b: one `EvidenceCandidate` per retrieval context (not per
  // passage) -- a passage that expands into more than one valid context
  // (e.g. both a `COMPARISON_LINKED` and `REPORT_ONLY` interpretation)
  // carries genuinely different citation/scope identity per context, and
  // the evidence-set builder's scope/coherence checks need that
  // distinction preserved, not collapsed.
  return contexts.map((context): EvidenceCandidate => {
    const lexical = lexicalByPassage.get(context.passageId) ?? null;
    const semantic = semanticByPassage.get(context.passageId) ?? null;
    const chunk = chunkParents.get(context.passageId) ?? null;
    const sources: EvidenceCandidateSource[] = [];
    if (lexical) sources.push("keyword");
    if (semantic) sources.push("semantic");
    if (chunk) sources.push("chunk");

    return {
      candidateId: context.contextId,
      passageId: context.passageId,
      retrievalContextId: context.contextId,
      context,
      citation: {
        publicationId: publicationId ?? "",
        retrievalContextId: context.contextId,
        passageId: context.passageId,
        passageComparisonId: context.passageComparisonId,
        reportComparisonId: context.reportComparisonId,
        reportSide: context.reportSide,
        reportId: context.reportId,
        firstPageNumber: context.firstPageNumber,
        lastPageNumber: context.lastPageNumber,
        label: formatCitationLabel(context),
      },
      sources,
      lexicalRankPosition: lexical?.rankPosition ?? null,
      semanticRawRank: semantic ? semantic.originalRank : null,
      semanticAdjustedRank: semantic ? semantic.finalRank : null,
      semanticRawSimilarity: semantic ? semantic.rawSimilarity : null,
      semanticAdjustedScore: semantic ? semantic.adjustedScore : null,
      qualityFactor: semantic ? semantic.qualityFactor : null,
      qualityExplanationCode: semantic ? semantic.explanationCode : null,
      rrfRank: rrfRankByPassage.get(context.passageId) ?? null,
      chunkStrategy: chunk?.bestStrategy ?? null,
      chunkRawRank: chunk?.bestRawRank ?? null,
      chunkSimilarity: chunk?.bestSimilarity ?? null,
      chunkHitCount: chunk?.hitCount ?? null,
    };
  });
}
