import type { QaChunkCandidate, QaEvidenceChunk } from "@/lib/domain/qa-chunk";
import type { QaChunkRepository } from "@/lib/repositories/qa-chunk-repository";
import type { QueryEmbeddingProvider } from "@/lib/services/query-embedding-provider";
import { getQaChunkConfig, type QaChunkConfig } from "@/lib/config/qa-chunk-config";
import { reciprocalRankFusion } from "@/lib/services/rrf";
import { buildQaEvidenceChunks, deduplicateQaChunkCandidates } from "@/lib/services/qa/qa-chunk-dedup";

export interface QaRetrievalResult {
  evidence: QaEvidenceChunk[];
  candidateCount: number;
  lexicalFusionUsed: boolean;
}

function mergeCandidateLists(
  semantic: readonly QaChunkCandidate[],
  lexical: readonly QaChunkCandidate[],
): QaChunkCandidate[] {
  const byId = new Map<string, QaChunkCandidate>();
  for (const c of semantic) byId.set(c.chunkId, { ...c });
  for (const c of lexical) {
    const existing = byId.get(c.chunkId);
    if (existing) {
      existing.lexicalRankPosition = c.lexicalRankPosition;
    } else {
      byId.set(c.chunkId, { ...c });
    }
  }
  return Array.from(byId.values());
}

/**
 * Milestone 7B.2 standard-RAG retrieval: bounded top-K semantic candidates,
 * optional lexical retrieval + deterministic RRF fusion, overlap-aware
 * dedup, citation resolution. Entirely separate from `/passages`'s
 * `retrieval-service.ts` -- `/passages` ranking is not touched by this
 * module, and this module never reads `qa_experiment`.
 */
export async function retrieveQaEvidence(
  questionText: string,
  embeddingProvider: QueryEmbeddingProvider,
  repository: QaChunkRepository,
  config: QaChunkConfig = getQaChunkConfig(),
  companyTicker: string | null = null,
): Promise<QaRetrievalResult> {
  const embedding = await embeddingProvider.embedQuery(questionText);
  const rawSemanticCandidates = await repository.searchSemanticCandidates(
    embedding.vector,
    config.semanticCandidateLimit,
    config.vectorSearchMode === "auto" ? "hnsw" : config.vectorSearchMode,
    companyTicker,
  );
  // HNSW/exact search always returns the K nearest neighbors regardless of
  // true relevance -- without a floor, a genuinely absent topic still
  // retrieves `semanticCandidateLimit` chunks and would look answerable
  // (confirmed live: 0% correct-abstention before this floor existed).
  // Applied ONLY for unscoped (corpus-wide/no-company) search: restricting
  // the ANN search to one company shrinks the candidate pool and lowers
  // the achievable max similarity for a genuinely relevant match (confirmed
  // live: a real, on-topic ACT chunk scored 0.706 company-scoped vs. 0.769
  // for the best unscoped match across all companies) -- applying the same
  // absolute, corpus-wide-calibrated threshold after scoping to one company
  // produced false INSUFFICIENT_EVIDENCE results for ordinary single-
  // company questions, exactly the case DOCUMENT_QA/COMPARISON_QA exist
  // for. The floor's actual job -- rejecting cross-topic drift -- matters
  // most when the search has nothing else narrowing it down.
  const semanticCandidates = companyTicker
    ? rawSemanticCandidates
    : rawSemanticCandidates.filter((c) => (c.similarity ?? 0) >= config.minimumSemanticSimilarity);

  let ranked: QaChunkCandidate[];
  let lexicalFusionUsed = false;

  if (config.lexicalFusionEnabled) {
    const lexicalCandidates = await repository.searchLexicalCandidates(
      questionText,
      config.lexicalCandidateLimit,
      companyTicker,
    );
    lexicalFusionUsed = lexicalCandidates.length > 0;

    const fused = reciprocalRankFusion(
      lexicalCandidates
        .filter((c) => c.lexicalRankPosition !== null)
        .map((c) => ({ id: c.chunkId, rankPosition: c.lexicalRankPosition as number })),
      semanticCandidates
        .filter((c) => c.semanticRankPosition !== null)
        .map((c) => ({ id: c.chunkId, rankPosition: c.semanticRankPosition as number })),
      config.rrfK,
    );
    const merged = mergeCandidateLists(semanticCandidates, lexicalCandidates);
    const byId = new Map(merged.map((c) => [c.chunkId, c]));
    ranked = fused
      .map((f): QaChunkCandidate | null => {
        const candidate = byId.get(f.id);
        if (!candidate) return null;
        return { ...candidate, fusedScore: f.fusedScore };
      })
      .filter((c): c is QaChunkCandidate => c !== null);
  } else {
    ranked = [...semanticCandidates].sort(
      (a, b) => (a.semanticRankPosition ?? Number.MAX_SAFE_INTEGER) - (b.semanticRankPosition ?? Number.MAX_SAFE_INTEGER),
    );
  }

  if (ranked.length === 0) {
    return { evidence: [], candidateCount: 0, lexicalFusionUsed };
  }

  const memberIds = await repository.resolveMemberPassageIds(ranked.map((c) => c.chunkId));
  const withMembers = ranked.map((c) => ({ ...c, memberPassageIds: memberIds.get(c.chunkId) ?? [] }));

  const groups = deduplicateQaChunkCandidates(withMembers, config.maxEvidenceChunks);
  const citations = await repository.resolveCitations(groups.map((g) => g.representative.chunkId));
  const evidence = buildQaEvidenceChunks(groups, citations);

  return { evidence, candidateCount: ranked.length, lexicalFusionUsed };
}
