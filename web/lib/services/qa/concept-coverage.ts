import type { EvidenceCandidate, QueryAnalysis } from "@/lib/domain/qa-evidence";
import { CONCEPT_FAMILIES, getConceptFamily, matchesFamily, matchesRestatementTerms } from "@/lib/domain/concept-families";

/**
 * Milestone 7B.1c Phase 3: deterministic per-candidate concept-coverage
 * features -- the input Phase 4's direct-responsiveness score is computed
 * from. Declared, fixed weights (no learned/tuned values):
 * - a required/optional family matched in the passage *body*
 *   (`context.text`) counts at full weight (1.0);
 * - matched only in the `heading` counts at a reduced weight (0.4) -- a
 *   heading naming a topic is real but weaker signal than the topic
 *   actually being discussed in the passage's own prose.
 */
export const BODY_MATCH_WEIGHT = 1.0;
export const HEADING_ONLY_MATCH_WEIGHT = 0.4;

export type ConceptMatchLocation = "body" | "heading_only";

export interface ConceptCoverage {
  matchedRequiredFamilies: string[];
  missingRequiredFamilies: string[];
  matchedOptionalFamilies: string[];
  /** Match location per matched required family id -- used by Phase 5's
   * "substantive body match unless the heading is clearly sufficient"
   * narrow-question rule. */
  matchLocationByFamily: Record<string, ConceptMatchLocation>;
  weightedRequiredCoverage: number;
  weightedOptionalCoverage: number;
  hasBodyMatch: boolean;
  hasAnyRequiredOrOptionalMatch: boolean;
  directionalCoverage: boolean;
  quantitativeCoverage: boolean;
  causalCoverage: boolean;
  ambiguityCoverage: boolean;
  /** Zero required/optional concept-family matches at all -- a passage that
   * is, at best, generic prose relative to what was actually asked. */
  genericOnlyIndicator: boolean;
  /** Right company (or right report side / right category), but zero
   * concept-family matches -- "company-only" is the specific, most common
   * case of the broader `scopeOnlyIndicator`. */
  companyOnlyIndicator: boolean;
  /** Any scope constraint (ticker, report side, or category) satisfied,
   * with zero concept-family matches -- per the milestone: "scope matches
   * alone provide zero substantive support." */
  scopeOnlyIndicator: boolean;
}

/** Causal coverage also accepts an explicit causal-explanation pattern --
 * a passage that explains why or what drove a change satisfies a causal
 * question even without the literal word "because". */
const CAUSAL_EXPLANATION_PATTERN = /\b(because|due to|driven by|as a result of|caused by|led to|reason for|attributable to)\b/i;

function familyCoverage(
  familyIds: readonly string[],
  bodyText: string,
  headingText: string,
): { matched: string[]; missing: string[]; locations: Record<string, ConceptMatchLocation>; weighted: number } {
  const matched: string[] = [];
  const missing: string[] = [];
  const locations: Record<string, ConceptMatchLocation> = {};
  let weightedSum = 0;

  for (const id of familyIds) {
    const family = getConceptFamily(id) ?? CONCEPT_FAMILIES.find((f) => f.id === id);
    if (!family) {
      missing.push(id);
      continue;
    }
    if (matchesFamily(family, bodyText)) {
      matched.push(id);
      locations[id] = "body";
      weightedSum += BODY_MATCH_WEIGHT;
    } else if (matchesFamily(family, headingText)) {
      matched.push(id);
      locations[id] = "heading_only";
      weightedSum += HEADING_ONLY_MATCH_WEIGHT;
    } else {
      missing.push(id);
    }
  }

  const weighted = familyIds.length > 0 ? weightedSum / familyIds.length : 1;
  return { matched, missing, locations, weighted };
}

export function computeConceptCoverage(candidate: EvidenceCandidate, analysis: QueryAnalysis): ConceptCoverage {
  const bodyText = candidate.context.text ?? "";
  const headingText = candidate.context.heading ?? "";

  const required = familyCoverage(analysis.requiredConceptFamilies, bodyText, headingText);
  // Optional families are Milestone-6 subcategories, tagged structurally on
  // the context rather than found by re-running text matching.
  const matchedOptionalFamilies = analysis.optionalConceptFamilies.filter((sub) => candidate.context.riskSubcategories.includes(sub));
  const weightedOptionalCoverage = analysis.optionalConceptFamilies.length > 0 ? matchedOptionalFamilies.length / analysis.optionalConceptFamilies.length : 0;

  const hasAnyRequiredOrOptionalMatch = required.matched.length > 0 || matchedOptionalFamilies.length > 0;
  const hasBodyMatch = required.matched.some((id) => required.locations[id] === "body");

  const combinedText = `${headingText} ${bodyText}`;
  const directionalCoverage = analysis.directionalConcepts.length > 0 && (
    (analysis.directionalConcepts.includes("added") && candidate.context.alignmentStatus === "NEW") ||
    (analysis.directionalConcepts.includes("removed") && candidate.context.alignmentStatus === "REMOVED") ||
    (analysis.directionalConcepts.includes("changed") && candidate.context.alignmentStatus !== "UNCHANGED") ||
    // "increased"/"decreased" have no verifiable stored signal (see
    // `qa-evidence.ts`'s `ComparisonDirection` doc) -- any real evidence
    // on-topic for the question counts as coverage, never a verified
    // direction claim.
    ((analysis.directionalConcepts.includes("increased") || analysis.directionalConcepts.includes("decreased")) && hasAnyRequiredOrOptionalMatch)
  );
  const quantitativeCoverage = analysis.quantitativeConcepts.length > 0 && /\d/.test(bodyText);
  const causalCoverage = analysis.causalConcepts.length > 0 && CAUSAL_EXPLANATION_PATTERN.test(combinedText);
  const ambiguityCoverage =
    analysis.ambiguitySensitiveConcepts.length > 0 && (candidate.context.alignmentStatus === "AMBIGUOUS" || matchesRestatementTerms(combinedText));

  const genericOnlyIndicator = !hasAnyRequiredOrOptionalMatch;
  const tickerMatch = analysis.requiredTicker !== null && candidate.context.companyTicker === analysis.requiredTicker;
  const sideMatch = analysis.requiredReportSide !== null && candidate.context.reportSide === analysis.requiredReportSide;
  const categoryMatch = analysis.requiredCategory !== null && candidate.context.categories.includes(analysis.requiredCategory);
  const companyOnlyIndicator = genericOnlyIndicator && tickerMatch;
  const scopeOnlyIndicator = genericOnlyIndicator && (tickerMatch || sideMatch || categoryMatch);

  return {
    matchedRequiredFamilies: required.matched,
    missingRequiredFamilies: required.missing,
    matchedOptionalFamilies,
    matchLocationByFamily: required.locations,
    weightedRequiredCoverage: required.weighted,
    weightedOptionalCoverage,
    hasBodyMatch,
    hasAnyRequiredOrOptionalMatch,
    directionalCoverage,
    quantitativeCoverage,
    causalCoverage,
    ambiguityCoverage,
    genericOnlyIndicator,
    companyOnlyIndicator,
    scopeOnlyIndicator,
  };
}
