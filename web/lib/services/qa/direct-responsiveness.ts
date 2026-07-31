import type { EvidenceCandidate, QueryAnalysis, RerankedEvidenceCandidate } from "@/lib/domain/qa-evidence";
import { computeConceptCoverage, type ConceptCoverage } from "@/lib/services/qa/concept-coverage";

/**
 * Milestone 7B.1c Phase 4: the direct-responsiveness score -- deliberately
 * separate from lexical rank, cosine similarity, the semantic reranker's
 * quality-adjusted score, and the existing `quality_aware` QA reranker
 * score (`concept-coverage.ts`'s output feeds this, but nothing here
 * overwrites those raw scores; see `RerankedEvidenceCandidate`'s additive
 * new fields). Predeclared, fixed formula and weights -- no learned/tuned
 * values, no hidden per-question adjustment:
 *
 *   directResponsivenessScore = weightedRequiredCoverage * REQUIRED_WEIGHT
 *                              + weightedOptionalCoverage * OPTIONAL_WEIGHT
 *
 * ...then, if `applyGenericPenalty` and the candidate is generic/company/
 * scope-only (Phase 3), multiplied by `GENERIC_LANGUAGE_PENALTY_FACTOR`;
 * then, if `applyQueryTypeConditions`, zeroed for a quantitative/causal/
 * comparative question whose type-specific requirement isn't met (these are
 * correctness gates, not soft signals -- a quantitative question truly
 * needs a number, not "mostly a number").
 */
export const REQUIRED_COVERAGE_WEIGHT = 0.8;
export const OPTIONAL_COVERAGE_WEIGHT = 0.2;
export const GENERIC_LANGUAGE_PENALTY_FACTOR = 0.3;
/** Swept in Phase 10 -- this is the "full_gate" preset's floor. */
export const DEFAULT_DIRECT_RESPONSIVENESS_FLOOR = 0.35;

export interface DirectResponsivenessStrategyConfig {
  /** A required family match only counts if it's a body match (not
   * heading-only) unless the candidate has no body text at all -- Phase
   * 5's "substantive body match unless the heading is clearly sufficient". */
  requireBodyMatch: boolean;
  applyGenericPenalty: boolean;
  applyQueryTypeConditions: boolean;
  directResponsivenessFloor: number;
}

export const FULL_GATE_STRATEGY_CONFIG: DirectResponsivenessStrategyConfig = {
  requireBodyMatch: true,
  applyGenericPenalty: true,
  applyQueryTypeConditions: true,
  directResponsivenessFloor: DEFAULT_DIRECT_RESPONSIVENESS_FLOOR,
};

export type IneligibilityReason =
  | "REQUIRED_CONCEPT_MISSING"
  | "GENERIC_ONLY_MATCH"
  | "COMPANY_ONLY_MATCH"
  | "SCOPE_ONLY_MATCH"
  | "BODY_SUPPORT_MISSING"
  | "QUANTITATIVE_REQUIREMENT_UNMET"
  | "CAUSAL_REQUIREMENT_UNMET"
  | "DIRECTIONAL_REQUIREMENT_UNMET"
  | "DIRECT_RESPONSIVENESS_BELOW_FLOOR";

export interface DirectResponsivenessResult {
  coverage: ConceptCoverage;
  conceptCoverageScore: number;
  directResponsivenessScore: number;
  eligible: boolean;
  ineligibilityReasons: IneligibilityReason[];
}

export function computeDirectResponsiveness(
  candidate: EvidenceCandidate,
  analysis: QueryAnalysis,
  config: DirectResponsivenessStrategyConfig = FULL_GATE_STRATEGY_CONFIG,
): DirectResponsivenessResult {
  const coverage = computeConceptCoverage(candidate, analysis);
  const reasons: IneligibilityReason[] = [];

  const conceptCoverageScore = coverage.weightedRequiredCoverage * REQUIRED_COVERAGE_WEIGHT + coverage.weightedOptionalCoverage * OPTIONAL_COVERAGE_WEIGHT;
  let score = conceptCoverageScore;

  if (analysis.requiredConceptFamilies.length > 0 && coverage.missingRequiredFamilies.length === analysis.requiredConceptFamilies.length) {
    reasons.push("REQUIRED_CONCEPT_MISSING");
  }

  if (config.requireBodyMatch && analysis.requiredConceptFamilies.length > 0 && !coverage.hasBodyMatch) {
    // A heading-only match (or no match) never clears the body-support
    // requirement, unless the family list is empty (nothing to require).
    reasons.push("BODY_SUPPORT_MISSING");
  }

  if (config.applyGenericPenalty && (coverage.genericOnlyIndicator || coverage.companyOnlyIndicator || coverage.scopeOnlyIndicator)) {
    score *= GENERIC_LANGUAGE_PENALTY_FACTOR;
    if (coverage.companyOnlyIndicator) reasons.push("COMPANY_ONLY_MATCH");
    else if (coverage.scopeOnlyIndicator) reasons.push("SCOPE_ONLY_MATCH");
    else reasons.push("GENERIC_ONLY_MATCH");
  }

  if (config.applyQueryTypeConditions) {
    if (analysis.quantitativeConcepts.length > 0 && !coverage.quantitativeCoverage) {
      score = 0;
      reasons.push("QUANTITATIVE_REQUIREMENT_UNMET");
    }
    if (analysis.causalConcepts.length > 0 && !coverage.causalCoverage) {
      score = 0;
      reasons.push("CAUSAL_REQUIREMENT_UNMET");
    }
    if (analysis.directionalConcepts.length > 0 && !coverage.directionalCoverage) {
      score = 0;
      reasons.push("DIRECTIONAL_REQUIREMENT_UNMET");
    }
  }

  const eligible = score >= config.directResponsivenessFloor && reasons.length === 0;
  if (!eligible && score < config.directResponsivenessFloor) reasons.push("DIRECT_RESPONSIVENESS_BELOW_FLOOR");

  return { coverage, conceptCoverageScore, directResponsivenessScore: score, eligible, ineligibilityReasons: reasons };
}

/**
 * Enriches every reranked candidate with its direct-responsiveness score
 * and eligibility -- run unconditionally, regardless of which of the four
 * `QaRerankerMethod`s determined `relevanceScore`/`relevanceRank` (Phase
 * 4's declared strategy #7: "score used only for eligibility"). When
 * `drivesRanking` is set (strategy #8: "score used for reranking plus
 * eligibility" -- Phase 10's `full_gate*` presets), candidates are
 * re-sorted by `directResponsivenessScore` and `directResponsivenessRank`
 * becomes the effective rank Phase 5/9 read; `relevanceRank` itself is
 * never overwritten, so the original reranker's ordering stays inspectable.
 */
export function enrichWithDirectResponsiveness(
  candidates: readonly EvidenceCandidate[] | readonly RerankedEvidenceCandidate[],
  analysis: QueryAnalysis,
  config: DirectResponsivenessStrategyConfig,
  drivesRanking: boolean,
): RerankedEvidenceCandidate[] {
  const withScores = candidates.map((candidate) => {
    const result = computeDirectResponsiveness(candidate, analysis, config);
    const base = candidate as Partial<RerankedEvidenceCandidate>;
    return {
      ...candidate,
      relevanceScore: base.relevanceScore ?? 0,
      relevanceRank: base.relevanceRank ?? 0,
      rerankerMethod: base.rerankerMethod ?? "baseline",
      numericFragmentSeverity: base.numericFragmentSeverity ?? null,
      conceptCoverageScore: result.conceptCoverageScore,
      directResponsivenessScore: result.directResponsivenessScore,
      directResponsivenessRank: 0,
      evidenceEligible: result.eligible,
      ineligibilityReasons: result.ineligibilityReasons,
    } satisfies RerankedEvidenceCandidate;
  });

  const ranked = drivesRanking
    ? [...withScores].sort((a, b) => b.directResponsivenessScore - a.directResponsivenessScore || a.candidateId.localeCompare(b.candidateId))
    : [...withScores].sort((a, b) => a.relevanceRank - b.relevanceRank || a.candidateId.localeCompare(b.candidateId));

  return ranked.map((candidate, index) => ({
    ...candidate,
    directResponsivenessRank: index + 1,
    ...(drivesRanking ? { relevanceScore: candidate.directResponsivenessScore, relevanceRank: index + 1 } : {}),
  }));
}
