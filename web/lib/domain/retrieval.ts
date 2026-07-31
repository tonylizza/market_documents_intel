import type {
  AlignmentStatus,
  AlignmentType,
  Confidence,
  HighlightSpan,
  PassageSearchParams,
  PassageType,
  ReportSide,
  StructuredContentCategory,
} from "@/lib/domain/passage";
import type { RawQuality } from "@/lib/domain/quality";
import type { QualityExplanationCode } from "@/lib/services/passage-quality";

/**
 * The three user-facing search modes (Milestone 7B.1). `keyword` is
 * unchanged existing lexical search; `semantic`/`hybrid` are new. Which mode
 * is the *default* when a user hasn't chosen one is a server-configured
 * decision (`PASSAGE_SEARCH_DEFAULT_MODE`), not a hardcoded constant here --
 * see `lib/config/retrieval-config.ts`.
 */
export type RetrievalMode = "keyword" | "semantic" | "hybrid";

export const RETRIEVAL_MODES: readonly RetrievalMode[] = ["keyword", "semantic", "hybrid"];

/** Server-side vector search strategy -- never exposed as an ordinary user
 * control (see milestone: "Expose it only through server configuration,
 * technical diagnostics, benchmark output"). */
export type VectorSearchMode = "exact" | "hnsw" | "auto";

/** A validated query-embedding call result. `model`/`modelRevision` let a
 * caller detect a mismatch against the corpus's stored vectors before ever
 * comparing them. */
export interface QueryEmbedding {
  vector: number[];
  model: string;
  modelRevision: string;
  dimensions: number;
  normalizedQueryText: string;
  latencyMs: number;
  tokenCount: number | null;
  provider: string;
}

/** Extends the existing, validated `PassageSearchParams` with the
 * additional inputs semantic/hybrid retrieval needs. Every existing
 * structured filter on `PassageSearchParams` still applies -- this is an
 * addition, not a replacement. */
export interface SemanticSearchParams extends PassageSearchParams {
  mode: RetrievalMode;
}

/** One passage-embedding nearest-neighbor candidate, before context
 * expansion. Never sent to the browser -- similarity is exposed on the
 * final `RetrievalResult`, the raw candidate shape is not.
 *
 * Milestone 7B.1a: carries the passage-level fields
 * `SemanticReranker`/`lib/services/passage-quality.ts` need to compute
 * deterministic quality features, without a second database round trip --
 * these all come from columns the candidate query already joins
 * (`app.current_passages`) or a cheap `EXISTS`
 * (`hasLanguageSignal`)/aggregate (`headingFrequency`) alongside it. */
export interface SemanticCandidate {
  passageId: string;
  similarity: number;
  heading: string | null;
  text: string;
  wordCount: number;
  hasLanguageSignal: boolean;
  headingFrequency: number;
}

/** One semantic candidate after `SemanticReranker.rerank` -- preserves the
 * raw cosine similarity and original (raw-similarity) rank separately from
 * the quality-adjusted score and final rank, per the milestone's
 * requirement that adjusted ranking is never confused with or labeled as
 * cosine similarity. */
export interface RerankedSemanticCandidate {
  passageId: string;
  rawSimilarity: number;
  qualityFactor: number;
  adjustedScore: number;
  explanationCode: QualityExplanationCode;
  originalRank: number;
  finalRank: number;
}

export interface LexicalCandidate {
  passageId: string;
  passageComparisonId: string | null;
  rank: number;
  /** 1-based position in the lexical ranking -- what RRF actually fuses on,
   * not the raw `ts_rank` score (see `lib/services/rrf.ts`). */
  rankPosition: number;
}

/** One `(passage, report comparison, report side)` retrieval context,
 * expanded from a `SemanticCandidate`/`LexicalCandidate` passage id via
 * `app.current_retrieval_contexts`. A single passage can legitimately
 * expand into more than one `RetrievalContext` (see Option C: one
 * deduplicated vector, multiple valid comparison-side interpretations). */
export interface RetrievalContext {
  contextId: string;
  passageId: string;
  contextType: "COMPARISON_LINKED" | "REPORT_ONLY";
  passageComparisonId: string | null;
  reportComparisonId: string | null;
  reportId: string;
  companyId: string;
  companyTicker: string;
  companyName: string;
  reportSide: ReportSide | null;
  alignmentStatus: AlignmentStatus | null;
  alignmentType: AlignmentType | null;
  confidence: Confidence | null;
  reportPeriodEnd: string | null;
  earlierPeriodEnd: string | null;
  laterPeriodEnd: string | null;
  heading: string | null;
  passageType: PassageType;
  structuredContentCategory: StructuredContentCategory | null;
  primaryNarrativeEligible: boolean;
  featureEligible: boolean;
  reportSideQuality: RawQuality | null;
  alignmentChangeQuality: RawQuality | null;
  collisionFlag: boolean;
  splitMergeFlag: boolean;
  irregularGapFlag: boolean;
  firstPageNumber: number;
  lastPageNumber: number;
  wordCount: number;
  text: string;
  categories: string[];
  riskSubcategories: string[];
}

/** A stable citation identity -- Milestone 7B.2 (grounded Q&A) can cite a
 * result directly from these fields without re-deriving anything. */
export interface RetrievalCitation {
  publicationId: string;
  retrievalContextId: string;
  passageId: string;
  passageComparisonId: string | null;
  reportComparisonId: string | null;
  reportSide: ReportSide | null;
  reportId: string;
  firstPageNumber: number;
  lastPageNumber: number;
  /** Server-formatted, e.g. "KP2, 2023->2024 comparison, later report, pp. 43-44". */
  label: string;
}

/** How strongly a semantic/hybrid result matched, derived from the
 * evaluation-informed weak-match policy (`lib/config/retrieval-config.ts`).
 * Never described to a user as a probability or confidence percentage. */
export type RetrievalStrength = "strong" | "weak";

export interface RetrievalDiagnostics {
  mode: RetrievalMode;
  vectorSearchMode: VectorSearchMode | null;
  /** Raw cosine similarity -- never adjusted, never relabeled. Weak-match
   * strength is judged against this value, not the adjusted score. */
  semanticSimilarity: number | null;
  /** Milestone 7B.1a: the deterministic retrieval-quality adjustment
   * applied on top of raw similarity to counter short-passage similarity
   * inflation -- see `lib/services/semantic-reranker.ts`. `null` for a
   * pure-lexical (Keyword) result, or a hybrid result with no semantic
   * component. */
  qualityFactor: number | null;
  adjustedSemanticScore: number | null;
  qualityExplanationCode: QualityExplanationCode | null;
  semanticRawRank: number | null;
  semanticAdjustedRank: number | null;
  lexicalRankPosition: number | null;
  fusedScore: number | null;
  model: string | null;
  modelRevision: string | null;
  strength: RetrievalStrength | null;
}

/** One ranked, citation-ready `/passages` result. `context` carries the
 * highest-ranked interpretation for this passage; `additionalContexts`
 * preserves every other valid context the same passage also occupies
 * (grouped, not discarded -- see milestone "Comparison-context expansion"). */
export interface RetrievalResult {
  context: RetrievalContext;
  additionalContexts: RetrievalContext[];
  excerpt: HighlightSpan[];
  headingHighlight: HighlightSpan[] | null;
  citation: RetrievalCitation;
  diagnostics: RetrievalDiagnostics;
  evidenceUrl: string;
  passageDetailUrl: string | null;
  finalRank: number;
}

export interface GroupedRetrievalResult extends RetrievalResult {
  hasAdditionalContexts: boolean;
}

export interface RetrievalPage {
  results: GroupedRetrievalResult[];
  mode: RetrievalMode;
  weakMatchNotice: boolean;
  providerUnavailable: boolean;
}
