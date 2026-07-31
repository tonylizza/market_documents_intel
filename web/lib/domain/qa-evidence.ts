import type { AlignmentStatus, ReportSide } from "@/lib/domain/passage";
import type { RetrievalCitation, RetrievalContext, RetrievalMode } from "@/lib/domain/retrieval";
import type { QualityExplanationCode } from "@/lib/services/passage-quality";

/**
 * Milestone 7B.1b: Q&A evidence-selection and groundedness-gating domain
 * types. Deliberately kept in their own file, separate from
 * `domain/passage.ts`'s `ComparisonEvidence*` types -- those describe passage
 * alignment rows within one report comparison (an existing, unrelated
 * concept); everything here describes evidence assembled in response to an
 * analyst question. No answer text appears anywhere in this file -- this
 * milestone selects and grades evidence, it does not generate answers.
 */

export type QuestionType =
  | "descriptive"
  | "comparative"
  | "chronological"
  | "existence_based"
  | "quantitative"
  | "causal";

export type RequestedScope = "single_company" | "single_comparison" | "corpus_wide";

/** Lexical-only: extracted from the question's wording, never verified
 * against any stored ground truth. No field in the research or publication
 * schema records whether a financial figure increased or decreased --
 * confirmed by direct inspection of the alignment/language-feature models
 * (Milestone 7B.1b pre-coding investigation). Any consumer of this value
 * must treat it as a ranking hint, never as a verified fact. */
export type ComparisonDirection = "increased" | "decreased" | "added" | "removed" | "changed" | null;

export interface QueryAnalysis {
  question: string;
  normalizedQuestion: string;
  /** Company tickers matched against the real, closed 6-company vocabulary
   * (`app.current_companies`) -- exact ticker match or company-name
   * substring match, never a fuzzy/inferred guess. */
  tickers: string[];
  dateRange: { start: string | null; end: string | null } | null;
  comparisonDirection: ComparisonDirection;
  /** Always "LEXICAL_ONLY" when `comparisonDirection` is non-null -- there is
   * no stored signal to verify direction against, so no other confidence
   * level is ever produced. */
  directionConfidence: "LEXICAL_ONLY" | null;
  alignmentStatuses: AlignmentStatus[];
  requestedReportSides: ReportSide[];
  categories: string[];
  subcategories: string[];
  questionType: QuestionType;
  requestedScope: RequestedScope;
  /** Hard requirements the evidence set must satisfy for the gate's
   * scope/side checks -- distinct from `tickers`/`requestedReportSides` above
   * (which record what was *extracted*), this records what's actually
   * *required* for the question to be considered in-scope. A question
   * mentioning a company only in passing (e.g. "how does this compare to
   * peers like ACT?") extracts the ticker but does not require it. */
  requiredTicker: string | null;
  requiredReportSide: ReportSide | null;
  requiredCategory: string | null;
  /** Terms that looked like they might be a company/date/category reference
   * but couldn't be resolved against the controlled vocabularies -- surfaced
   * explicitly rather than silently dropped, per the milestone's "must not
   * silently narrow scope incorrectly" requirement. */
  unresolvedTerms: string[];
  warnings: string[];

  // -- Milestone 7B.1c: substantive-concept analysis, deliberately separate
  // from the scope fields above (tickers/dateRange/requestedReportSides/
  // requiredCategory) -- those describe *who/when/where* the question is
  // about, these describe *what it actually asks*. See
  // `lib/domain/concept-families.ts`.
  /** One or more independently-checkable clauses the question decomposes
   * into (Phase 6's "separable material elements") -- most questions have
   * exactly one. Each element's `requiredFamilies` feeds
   * `requiredConceptFamilies` (their union) and, for multi-element
   * questions, the gate's supported/unsupported-subquestion split. */
  materialElements: { text: string; requiredFamilies: string[] }[];
  /** Union of every material element's matched `ConceptFamily` ids --
   * substantive topics the evidence must actually cover, never satisfied by
   * scope (company/date/side/category) alone. */
  requiredConceptFamilies: string[];
  /** Corroborating-only concept families (currently: the existing
   * Milestone-6 `categories`/`subcategories` taxonomy) -- present is a
   * bonus, never load-bearing for eligibility. */
  optionalConceptFamilies: string[];
  /** Non-empty exactly when `comparisonDirection` is non-null -- kept as its
   * own field (rather than requiring callers to know that encoding) so
   * Phase 4/8 code reads a concept list, not a nullable enum. */
  directionalConcepts: string[];
  /** Non-empty when `questionType === "quantitative"`. */
  quantitativeConcepts: string[];
  /** Non-empty when `questionType === "causal"`. */
  causalConcepts: string[];
  /** Restatement/correction vocabulary matched anywhere in the question
   * (`RESTATEMENT_CORRECTION_TERMS`) -- drives Phase 7's chronology/
   * supersession handling. */
  ambiguitySensitiveConcepts: string[];
  /** Material elements (2+ -element questions only) whose text looks like a
   * distinct, substantive ask but matched zero concept families -- surfaced
   * rather than silently treated as "nothing required," per the milestone's
   * standing "never silently drop" rule. */
  unresolvedRequiredConcepts: string[];
}

export type EvidenceCandidateSource = "keyword" | "semantic" | "phrase" | "category_filtered" | "chunk";

/** One candidate before second-stage reranking -- carries full retrieval
 * provenance from whichever source(s) produced it, never re-derived or
 * discarded. A candidate found by more than one source (e.g. both keyword
 * and semantic) is merged into a single entry with all provenance fields
 * populated, not duplicated. */
export interface EvidenceCandidate {
  candidateId: string;
  passageId: string;
  retrievalContextId: string;
  context: RetrievalContext;
  citation: RetrievalCitation;
  sources: EvidenceCandidateSource[];
  lexicalRankPosition: number | null;
  semanticRawRank: number | null;
  semanticAdjustedRank: number | null;
  semanticRawSimilarity: number | null;
  semanticAdjustedScore: number | null;
  qualityFactor: number | null;
  qualityExplanationCode: QualityExplanationCode | null;
  rrfRank: number | null;
  /** Milestone 7B.1d (experimental): non-null only when this passage was
   * (also) surfaced by mapping a Q&A retrieval-chunk child hit back to its
   * parent canonical passage -- see `qa-chunk-retrieval-repository.ts` and
   * `candidate-generation.ts`'s optional `chunkOptions` parameter. `null`
   * for every candidate produced by the shipped keyword/semantic path,
   * which never sets these fields -- this is purely additive, evaluation-
   * only provenance, never combined with `semanticRawSimilarity` without
   * an explicit, predeclared fusion rule (see `qa-chunk-fusion.ts`). */
  chunkStrategy?: string | null;
  chunkRawRank?: number | null;
  chunkSimilarity?: number | null;
  /** Number of distinct child chunks (any strategy) that mapped to this
   * passage -- overlapping chunks increase this diagnostic count but never
   * inflate the evidence set itself (deduplication happens by `passageId`
   * in `evidence-set-builder.ts`, unchanged by this milestone). */
  chunkHitCount?: number | null;
}

export type QaRerankerMethod = "baseline" | "concept_coverage" | "quality_aware";

export interface RerankedEvidenceCandidate extends EvidenceCandidate {
  relevanceScore: number;
  relevanceRank: number;
  rerankerMethod: QaRerankerMethod;
  /** Present only for candidates the quality-aware reranker evaluated;
   * `null` for the baseline/concept-coverage methods, which don't compute
   * per-passage quality features. */
  numericFragmentSeverity: "none" | "fragment_with_context" | "fragment_without_context" | null;

  // -- Milestone 7B.1c Phase 4: direct-responsiveness enrichment, computed
  // for every candidate regardless of which `rerankerMethod` determined
  // `relevanceScore`/`relevanceRank` above -- additive fields, never
  // overwriting any raw retrieval/reranking score. See
  // `lib/services/qa/direct-responsiveness.ts`.
  conceptCoverageScore: number;
  directResponsivenessScore: number;
  directResponsivenessRank: number;
  evidenceEligible: boolean;
  ineligibilityReasons: string[];
}

export type EvidenceRejectionReason =
  | "DUPLICATE"
  | "BELOW_RELEVANCE_FLOOR"
  | "OUT_OF_SCOPE"
  | "REDUNDANT_NO_NEW_COVERAGE"
  /** Milestone 7B.1c Phase 5: narrow-question candidates that fail the
   * direct-responsiveness eligibility floor (`evidenceEligible === false`)
   * -- distinct from `OUT_OF_SCOPE` (wrong company/side/category) and
   * `BELOW_RELEVANCE_FLOOR` (raw semantic similarity too low): this
   * candidate is in-scope and similar enough to retrieve, but not actually
   * about what was asked. */
  | "NOT_DIRECTLY_RESPONSIVE";

export interface EvidenceRejection {
  candidateId: string;
  passageId: string;
  retrievalContextId: string;
  reason: EvidenceRejectionReason;
}

export interface SelectedEvidence extends RerankedEvidenceCandidate {
  selectionOrder: number;
  newFacetsCovered: string[];
}

export interface EvidenceCoverage {
  requiredFacets: string[];
  coveredFacets: string[];
  coverageRatio: number;
}

export interface EvidenceCoherence {
  conflictingPeriods: boolean;
  mixedAlignmentWithoutExplanation: boolean;
  duplicateCountedAsIndependent: boolean;
  outOfRangeEvidence: boolean;
  hasContradiction: boolean;

  // -- Milestone 7B.1c Phase 7/8: restatement, comparison, and chronology
  // safeguards. All default `false`/empty when `restatementSafeguards` is
  // disabled (Phase 10 presets before `full_gate_restatement_safeguards`).
  /** A restatement/correction-flagged passage was selected without clear
   * EARLIER/LATER chronology, or without an explanatory link between an
   * original and a restated value. */
  restatementAmbiguityDetected: boolean;
  /** `true` when chronology between original/restated evidence is clear
   * (explicit, differing report sides); `false` when ambiguous; `null` when
   * no restatement signal was present at all. */
  restatementChronologyClear: boolean | null;
  /** Passage ids of selected evidence an explanatory link marks as
   * superseded by a later selected passage -- kept in the set (never
   * silently excluded) but flagged. */
  supersededPassageIds: string[];
  /** Comparative questions only: `true` when the requested EARLIER/LATER
   * sides are both represented in selected evidence and share a required
   * concept family; `false` when a side is missing or topically mismatched. */
  comparisonContextSatisfied: boolean | null;
  /** Chronological questions only: `true` when the requested date range is
   * covered by at least one selected passage's period. */
  dateRangeCovered: boolean | null;
}

export interface EvidenceSet {
  selected: SelectedEvidence[];
  rejected: EvidenceRejection[];
  coverage: EvidenceCoverage;
}

export type GateStatus = "SUPPORTED" | "PARTIALLY_SUPPORTED" | "INSUFFICIENT_EVIDENCE" | "AMBIGUOUS_OR_CONFLICTING";

export type GateReasonCode =
  | "NO_DIRECT_EVIDENCE"
  | "ONLY_WEAK_INDIRECT_EVIDENCE"
  | "REQUIRED_SCOPE_NOT_COVERED"
  | "MISSING_COMPARISON_SIDE"
  | "NUMERIC_FRAGMENT_WITHOUT_CONTEXT"
  | "CONFLICTING_EVIDENCE"
  | "INSUFFICIENT_TOPIC_COVERAGE"
  | "LOW_RELEVANCE_MARGIN"
  | "CITATION_METADATA_INCOMPLETE"
  | "EVIDENCE_REDUNDANT"
  | "SUPPORTED_BY_SINGLE_PASSAGE"
  | "SUPPORTED_BY_MULTIPLE_PASSAGES"
  // -- Milestone 7B.1c Phase 9 gate reassembly
  | "REQUIRED_CONCEPT_MISSING"
  | "GENERIC_ONLY_MATCH"
  | "COMPANY_ONLY_MATCH"
  | "SCOPE_ONLY_MATCH"
  | "BODY_SUPPORT_MISSING"
  | "DIRECT_RESPONSIVENESS_BELOW_FLOOR"
  | "PARTIAL_SUPPORT_NOT_SEPARABLE"
  | "WRONG_TOPIC_RIGHT_COMPANY"
  | "RESTATEMENT_AMBIGUITY"
  | "CHRONOLOGY_INCOMPLETE"
  // -- Phase 7: restatement/correction
  | "RESTATEMENT_DETECTED"
  | "ORIGINAL_AND_RESTATED_VALUES_PRESENT"
  | "SUPERSEDED_EVIDENCE"
  | "CORRECTION_CONTEXT_REQUIRED"
  | "RESTATEMENT_CHRONOLOGY_CLEAR"
  | "RESTATEMENT_CHRONOLOGY_AMBIGUOUS"
  // -- Phase 8: comparative/chronological safeguards
  | "COMPARISON_CONTEXT_MISSING"
  | "REPORT_SIDE_MISMATCH"
  | "DIRECTION_NOT_VERIFIED"
  | "DATE_RANGE_NOT_COVERED"
  | "CHRONOLOGY_CONFLICT"
  | "COMPARISON_TOPIC_MISMATCH";

export interface GroundednessSignals {
  distinctPassageCount: number;
  strongEvidenceCount: number;
  requiredScopeSatisfied: boolean;
  requiredSideSatisfied: boolean;
  citationComplete: boolean;
  topicCoverageRatio: number;
  topScoreMargin: number;
  numericFragmentWithoutContextRatio: number;
  redundancyRatio: number;
  contradictionDetected: boolean;
  /** Count of selected evidence items with `evidenceEligible === true`
   * (Phase 4/9) -- distinct from `strongEvidenceCount`, which measures raw
   * retrieval-score strength, not topical direct-responsiveness. */
  directlyResponsiveCount: number;
}

export interface GateDecision {
  status: GateStatus;
  reasonCodes: GateReasonCode[];
  signals: GroundednessSignals;
  /** Phase 6: material elements (from `QueryAnalysis.materialElements`)
   * that selected evidence directly supports. Equal to all elements for a
   * single-element `SUPPORTED` question. */
  supportedSubquestions: string[];
  /** Phase 6: material elements selected evidence does not support --
   * non-empty only for `PARTIALLY_SUPPORTED`/`INSUFFICIENT_EVIDENCE`. */
  unsupportedSubquestions: string[];
  /** Phase 6: human-readable explanation of the supported/unsupported
   * split -- always present, even when there's only one element (in which
   * case it explains why that single element is or isn't supported). */
  partialSupportRationale: string;
}

export interface EvidencePackage {
  evidenceSelectionVersion: string;
  publicationId: string;
  question: string;
  normalizedQuestion: string;
  queryAnalysis: QueryAnalysis;
  gateStatus: GateStatus;
  gateReasonCodes: GateReasonCode[];
  selectedEvidence: SelectedEvidence[];
  rejectedEvidenceSummary: { reason: EvidenceRejectionReason; count: number }[];
  coverage: EvidenceCoverage;
  coherence: EvidenceCoherence;
  supportedSubquestions: string[];
  unsupportedSubquestions: string[];
  partialSupportRationale: string;
  retrievalDiagnostics: { candidateCount: number; sources: EvidenceCandidateSource[]; retrievalMode: RetrievalMode | null };
  rerankerMethod: QaRerankerMethod;
  generatedAt: string;
  latencyMs: {
    queryAnalysis: number;
    candidateGeneration: number;
    reranking: number;
    evidenceSetConstruction: number;
    groundednessGate: number;
    total: number;
  };
}
