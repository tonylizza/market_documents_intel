import type { EvidenceCandidate, QaRerankerMethod, QueryAnalysis, RerankedEvidenceCandidate } from "@/lib/domain/qa-evidence";
import { computeNumericFragmentSeverity, computePassageQualityFeatures, computeQualityAdjustment } from "@/lib/services/passage-quality";

/**
 * Milestone 7B.1b: second-stage Q&A relevance reranking. Mirrors the
 * `SemanticReranker` pattern (`lib/services/semantic-reranker.ts`) -- a
 * small pluggable interface with several deterministic implementations
 * compared against each other on the real corpus before a default ships.
 * Deliberately deterministic-only this pass: no cross-encoder, no LLM
 * comparator (see the milestone plan's scope cut -- those are only built if
 * evaluation shows the deterministic baseline is clearly insufficient).
 */
export interface QaReranker {
  readonly method: QaRerankerMethod;
  rerank(question: string, candidates: readonly EvidenceCandidate[], analysis: QueryAnalysis): RerankedEvidenceCandidate[];
}

/** Exported for reuse by `candidate-generation.ts`'s lexical-query
 * construction -- one shared stopword list, not a second drifting copy. */
export const STOPWORDS = new Set([
  "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "is", "are", "was", "were", "did", "does",
  "what", "how", "why", "who", "which", "with", "about", "that", "this", "these", "those", "it", "its", "as", "at",
  "by", "from", "be", "has", "have", "had", "will", "would", "could", "should", "than", "then", "there", "their",
]);

export function extractConceptTerms(question: string): string[] {
  const tokens = question
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length >= 3 && !STOPWORDS.has(token));
  return [...new Set(tokens)];
}

function conceptCoverageScore(terms: readonly string[], candidate: EvidenceCandidate): number {
  if (terms.length === 0) return 0;
  const haystack = `${candidate.context.heading ?? ""} ${candidate.context.text}`.toLowerCase();
  const matched = terms.filter((term) => haystack.includes(term)).length;
  return matched / terms.length;
}

function stableSort(candidates: RerankedEvidenceCandidate[]): RerankedEvidenceCandidate[] {
  return [...candidates].sort((a, b) => {
    if (b.relevanceScore !== a.relevanceScore) return b.relevanceScore - a.relevanceScore;
    const rrfDiff = (a.rrfRank ?? Number.MAX_SAFE_INTEGER) - (b.rrfRank ?? Number.MAX_SAFE_INTEGER);
    if (rrfDiff !== 0) return rrfDiff;
    return a.candidateId.localeCompare(b.candidateId);
  });
}

/** Milestone 7B.1c Phase 4: placeholder direct-responsiveness fields for
 * the three pre-7B.1c rerankers -- always overwritten by
 * `enrichWithDirectResponsiveness` immediately after reranking in
 * `qa-pipeline.ts`/the evaluation scripts, never read before that
 * enrichment runs. Kept here (rather than making the fields optional on
 * `RerankedEvidenceCandidate`) so every other consumer of the type can
 * assume they're always populated. */
const UNENRICHED_DIRECT_RESPONSIVENESS_FIELDS = {
  conceptCoverageScore: 0,
  directResponsivenessScore: 0,
  directResponsivenessRank: 0,
  evidenceEligible: false,
  ineligibilityReasons: [] as string[],
};

function assignRanks(sorted: RerankedEvidenceCandidate[]): RerankedEvidenceCandidate[] {
  return sorted.map((candidate, index) => ({ ...candidate, relevanceRank: index + 1 }));
}

/** Pass-through of Phase C's fused (RRF) order -- the "no second-stage
 * reranking" comparison point. */
export class BaselineQaReranker implements QaReranker {
  readonly method: QaRerankerMethod = "baseline";

  rerank(_question: string, candidates: readonly EvidenceCandidate[], _analysis: QueryAnalysis): RerankedEvidenceCandidate[] {
    void _analysis;
    const scored = candidates.map(
      (candidate): RerankedEvidenceCandidate => ({
        ...candidate,
        relevanceScore: candidate.rrfRank ? 1 / candidate.rrfRank : 0,
        relevanceRank: 0,
        rerankerMethod: this.method,
        numericFragmentSeverity: null,
        ...UNENRICHED_DIRECT_RESPONSIVENESS_FIELDS,
      }),
    );
    return assignRanks(stableSort(scored));
  }
}

/** Scores candidates by the fraction of the question's significant
 * (non-stopword) terms that appear in the passage's heading/text --
 * deliberately simple lexical-overlap scoring, no embeddings, no ML. */
export class ConceptCoverageQaReranker implements QaReranker {
  readonly method: QaRerankerMethod = "concept_coverage";

  rerank(question: string, candidates: readonly EvidenceCandidate[], _analysis: QueryAnalysis): RerankedEvidenceCandidate[] {
    void _analysis;
    const terms = extractConceptTerms(question);
    const scored = candidates.map(
      (candidate): RerankedEvidenceCandidate => ({
        ...candidate,
        relevanceScore: conceptCoverageScore(terms, candidate),
        relevanceRank: 0,
        rerankerMethod: this.method,
        numericFragmentSeverity: null,
        ...UNENRICHED_DIRECT_RESPONSIVENESS_FIELDS,
      }),
    );
    return assignRanks(stableSort(scored));
  }
}

/** Combines concept coverage with the deterministic passage-quality
 * adjustment (`lib/services/passage-quality.ts`) -- reuses the already-
 * computed quality factor for semantic-sourced candidates, and computes one
 * fresh for keyword-only candidates that never went through the semantic
 * reranker. "Nearby context" for numeric-fragment classification is
 * determined within the bounded candidate set itself (same report, page
 * range within 1 page of another candidate) -- no new query. */
export class QualityAwareQaReranker implements QaReranker {
  readonly method: QaRerankerMethod = "quality_aware";

  rerank(question: string, candidates: readonly EvidenceCandidate[], _analysis: QueryAnalysis): RerankedEvidenceCandidate[] {
    void _analysis;
    const terms = extractConceptTerms(question);

    const scored = candidates.map((candidate): RerankedEvidenceCandidate => {
      const hasNearbyContext = candidates.some(
        (other) =>
          other.candidateId !== candidate.candidateId &&
          other.context.reportId === candidate.context.reportId &&
          Math.abs(other.context.firstPageNumber - candidate.context.firstPageNumber) <= 1,
      );
      const hasLanguageSignal = candidate.context.categories.length > 0 || candidate.context.riskSubcategories.length > 0;
      const features = computePassageQualityFeatures({
        heading: candidate.context.heading,
        text: candidate.context.text,
        wordCount: candidate.context.wordCount,
        hasLanguageSignal,
        headingFrequency: 0,
        hasNearbyContext,
      });
      const qualityFactor = candidate.qualityFactor ?? computeQualityAdjustment(features).factor;
      const coverage = conceptCoverageScore(terms, candidate);

      return {
        ...candidate,
        relevanceScore: coverage * qualityFactor,
        relevanceRank: 0,
        rerankerMethod: this.method,
        numericFragmentSeverity: computeNumericFragmentSeverity(features),
        ...UNENRICHED_DIRECT_RESPONSIVENESS_FIELDS,
      };
    });
    return assignRanks(stableSort(scored));
  }
}

export function createQaReranker(method: QaRerankerMethod): QaReranker {
  switch (method) {
    case "baseline":
      return new BaselineQaReranker();
    case "concept_coverage":
      return new ConceptCoverageQaReranker();
    case "quality_aware":
      return new QualityAwareQaReranker();
  }
}
