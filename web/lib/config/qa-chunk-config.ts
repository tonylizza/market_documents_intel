import "server-only";

/**
 * Milestone 7B.2 Q&A retrieval-chunk tuning -- separate from
 * `lib/config/retrieval-config.ts` (canonical-passage `/passages` search),
 * which this milestone must not alter. Every value is a server
 * configuration knob, read once per process from environment variables.
 */

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function envFloat(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export interface QaChunkConfig {
  /** Bounded top-K semantic candidates before fusion/dedup (brief:
   * "initially 20-30 semantic candidates"). */
  semanticCandidateLimit: number;
  /** Bounded top-K lexical candidates when lexical fusion is enabled. */
  lexicalCandidateLimit: number;
  /** Whether optional lexical retrieval + RRF fusion is enabled at all
   * (brief: "Add optional lexical retrieval ... If lexical fusion is
   * enabled, use deterministic reciprocal rank fusion"). */
  lexicalFusionEnabled: boolean;
  /** Reciprocal Rank Fusion constant, same default as `retrieval-config.ts`
   * for consistency -- no evidence yet justifies a different value for
   * chunk-level fusion specifically. */
  rrfK: number;
  /** Final deduplicated evidence-set size handed to answer generation
   * (brief: "Keep final evidence to roughly 3-5 deduplicated chunks"). */
  maxEvidenceChunks: number;
  vectorSearchMode: "exact" | "hnsw" | "auto";
  /** Below this cosine similarity, a semantic candidate is dropped before
   * fusion/dedup -- HNSW/exact search always returns the K nearest
   * neighbors regardless of true relevance, so an unbounded top-K alone
   * cannot express "no relevant chunk exists" (confirmed by a live 7B.2
   * evaluation run: 0% correct-abstention on genuinely absent-topic
   * questions before this floor was added -- see `evaluation/results/
   * qa_answer_evaluation.csv`). Reuses `retrieval-config.ts`'s
   * corpus-calibrated value (0.71, same embedding model, same corpus) --
   * not independently re-derived for chunk-level retrieval specifically,
   * which is a documented limitation, not a silent assumption.
   *
   * Applied by `qa-chunk-retrieval-service.ts::retrieveQaEvidence` ONLY
   * when the search is unscoped (no company filter) -- scoping to one
   * company shrinks the ANN candidate pool and lowers the achievable max
   * similarity for a genuinely relevant match, so the same absolute floor
   * applied after company-scoping produced false INSUFFICIENT_EVIDENCE
   * results on ordinary single-company questions (confirmed live: a real,
   * on-topic ACT chunk scored 0.706 company-scoped vs. 0.769 unscoped for
   * the best cross-company match on the same question). */
  minimumSemanticSimilarity: number;
}

export function getQaChunkConfig(): QaChunkConfig {
  return {
    semanticCandidateLimit: envInt("QA_CHUNK_SEMANTIC_CANDIDATE_LIMIT", 25),
    lexicalCandidateLimit: envInt("QA_CHUNK_LEXICAL_CANDIDATE_LIMIT", 25),
    lexicalFusionEnabled: process.env.QA_CHUNK_LEXICAL_FUSION_ENABLED === "true",
    rrfK: envInt("QA_CHUNK_RRF_K", 60),
    maxEvidenceChunks: envInt("QA_CHUNK_MAX_EVIDENCE", 5),
    vectorSearchMode: (process.env.QA_CHUNK_VECTOR_SEARCH_MODE as "exact" | "hnsw" | "auto") ?? "hnsw",
    minimumSemanticSimilarity: envFloat("QA_CHUNK_MIN_SIMILARITY", 0.71),
  };
}
