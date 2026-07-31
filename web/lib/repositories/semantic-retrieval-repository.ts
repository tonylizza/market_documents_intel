import type { LexicalCandidate, RetrievalContext, SemanticCandidate, VectorSearchMode } from "@/lib/domain/retrieval";
import type { PassageSearchParams } from "@/lib/domain/passage";

/**
 * Purpose-built retrieval methods -- no generic/arbitrary vector-query
 * execution is ever exposed (mirrors `PassageRepository`'s existing
 * discipline). Structured filters (`PassageSearchParams`'s non-text-query
 * fields) apply to every method here exactly as they already do for
 * lexical search.
 */
export interface SemanticRetrievalRepository {
  searchSemanticCandidates(
    vector: number[],
    params: PassageSearchParams,
    limit: number,
    mode: VectorSearchMode,
  ): Promise<SemanticCandidate[]>;

  searchLexicalCandidates(params: PassageSearchParams, limit: number): Promise<LexicalCandidate[]>;

  expandRetrievalContexts(passageIds: readonly string[], params: PassageSearchParams): Promise<RetrievalContext[]>;

  /** Resolves `"auto"` to a concrete `"exact" | "hnsw"` mode, based on the
   * corpus size actually observed -- never a hardcoded assumption (see
   * milestone: "Do not assume approximate retrieval is automatically faster
   * or preferable"). */
  resolveVectorSearchMode(configured: VectorSearchMode): Promise<"exact" | "hnsw">;
}
