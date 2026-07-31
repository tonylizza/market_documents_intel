import "server-only";
import type { RetrievalMode, VectorSearchMode } from "@/lib/domain/retrieval";
import { RETRIEVAL_MODES } from "@/lib/domain/retrieval";
import { DEFAULT_QUALITY_ADJUSTMENT_CONFIG } from "@/lib/services/passage-quality";

/**
 * Milestone 7B.1 retrieval tuning -- every value here is a *server*
 * configuration knob (see milestone: "Do not expose retrieval mode as an
 * ordinary user control"). Read once per process from environment
 * variables, with defaults chosen from the real-corpus benchmark recorded
 * in the Milestone 7B.1 report (`publication_retrieval_benchmark.csv`):
 * HNSW measured recall@10 = 1.0 (both filtered and unfiltered) against
 * exact, and ~30% lower unfiltered latency, so HNSW is the default vector
 * search mode -- exact remains available as the correctness baseline and
 * benchmark reference, never removed.
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

function envVectorSearchMode(name: string, fallback: VectorSearchMode): VectorSearchMode {
  const raw = process.env[name];
  if (raw === "exact" || raw === "hnsw" || raw === "auto") return raw;
  return fallback;
}

function envRetrievalMode(name: string, fallback: RetrievalMode): RetrievalMode {
  const raw = process.env[name];
  if (raw && (RETRIEVAL_MODES as readonly string[]).includes(raw)) return raw as RetrievalMode;
  return fallback;
}

export interface RetrievalConfig {
  /** How many nearest-neighbor passage-embedding candidates to retrieve
   * before context expansion/filtering/diversification. */
  semanticCandidateLimit: number;
  /** How many lexical candidates (ranked, not just the page) to retrieve
   * for hybrid fusion -- independent of the `/passages` page size. */
  lexicalCandidateLimit: number;
  /** Multiplier applied to the final requested result count when deciding
   * how many unique passages to fetch before expansion -- retrieving more
   * candidates than needed compensates for candidates that expand into
   * zero contexts (filtered out) or get capped by `contextsPerPassageCap`. */
  contextExpansionMultiplier: number;
  /** Maximum number of contexts from the same passage kept in one result
   * set (the rest are preserved as `additionalContexts`, never discarded,
   * but capped so one highly-similar passage can't flood the page). */
  contextsPerPassageCap: number;
  /** Reciprocal Rank Fusion constant (`1 / (k + rank)`), standard choice of
   * 60 unless evaluation demonstrates a better-justified value. */
  rrfK: number;
  /** Below this cosine similarity, a semantic/hybrid result is labeled a
   * weak match rather than presented as a confident finding. Derived from
   * the Milestone 7B.1 evaluation dataset's observed similarity
   * distribution (relevant vs. no-answer query similarity scores -- see the
   * final report) -- not an arbitrary constant chosen without examining
   * real data. */
  minimumSemanticSimilarity: number;
  vectorSearchMode: VectorSearchMode;
  defaultSearchMode: RetrievalMode;
  /** Milestone 7B.1a: bounded quality-adjustment multipliers for
   * `QualityAdjustedSemanticReranker` -- see `lib/services/passage-quality.ts`
   * and the Milestone 7B.1a report's remediation-experiment results for how
   * these defaults were selected. */
  headingOnlyFragmentFactor: number;
  genericHeadingFactor: number;
  lowSubstantiveFactor: number;
}

export function getRetrievalConfig(): RetrievalConfig {
  return {
    semanticCandidateLimit: envInt("SEMANTIC_CANDIDATE_LIMIT", 100),
    lexicalCandidateLimit: envInt("LEXICAL_CANDIDATE_LIMIT", 100),
    contextExpansionMultiplier: envInt("RETRIEVAL_CONTEXT_EXPANSION_MULTIPLIER", 3),
    contextsPerPassageCap: envInt("RETRIEVAL_CONTEXTS_PER_PASSAGE", 2),
    rrfK: envInt("RETRIEVAL_RRF_K", 60),
    // Milestone 7B.1a recalibration: the Milestone 7B.1 value (0.71) was
    // derived from only 2 no-answer cases -- re-swept against 10 real
    // no-answer cases (mean top-1 similarity 0.736, max 0.816) and 40
    // answerable cases (mean 0.827, min 0.731) from the expanded 83-case
    // dataset. 0.71 remains the best zero-suppression-cost point (no
    // answerable case is ever misclassified as weak at this threshold), but
    // the two distributions overlap substantially -- no threshold on raw
    // similarity alone cleanly separates them at this corpus's short-
    // fragment density. At 0.71, 6/10 no-answer cases still produce a
    // top-1 similarity above the threshold (a "false strong match"); pushing
    // higher (e.g. 0.78) cuts that to 1/10 but starts wrongly suppressing
    // ~17.5% of genuinely answerable cases. Kept at 0.71 (zero suppression
    // cost) rather than trading in answerable-case reliability for a
    // marginal no-answer improvement -- see the Milestone 7B.1a final report
    // for the full threshold sweep and the resulting 7B.2 readiness caveat.
    minimumSemanticSimilarity: envFloat("RETRIEVAL_MIN_SIMILARITY", 0.71),
    vectorSearchMode: envVectorSearchMode("SEMANTIC_RETRIEVAL_MODE", "hnsw"),
    defaultSearchMode: envRetrievalMode("PASSAGE_SEARCH_DEFAULT_MODE", "keyword"),
    headingOnlyFragmentFactor: envFloat(
      "RETRIEVAL_HEADING_ONLY_FRAGMENT_FACTOR",
      DEFAULT_QUALITY_ADJUSTMENT_CONFIG.headingOnlyFragmentFactor,
    ),
    genericHeadingFactor: envFloat(
      "RETRIEVAL_GENERIC_HEADING_FACTOR",
      DEFAULT_QUALITY_ADJUSTMENT_CONFIG.genericHeadingFactor,
    ),
    lowSubstantiveFactor: envFloat(
      "RETRIEVAL_LOW_SUBSTANTIVE_FACTOR",
      DEFAULT_QUALITY_ADJUSTMENT_CONFIG.lowSubstantiveFactor,
    ),
  };
}
