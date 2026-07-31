import type {
  EvidenceCoverage,
  EvidenceRejection,
  EvidenceSet,
  QueryAnalysis,
  RerankedEvidenceCandidate,
  SelectedEvidence,
} from "@/lib/domain/qa-evidence";
import { getRetrievalConfig } from "@/lib/config/retrieval-config";
import type { QaConfig } from "@/lib/config/qa-config";

/**
 * Milestone 7B.1b: deterministic evidence-set construction. Every rejection
 * carries an explicit reason (never silently dropped). Reuses the existing
 * corpus weak-match floor (`minimumSemanticSimilarity`) rather than
 * inventing a second, competing relevance threshold -- applied narrowly
 * (see `isBelowRelevanceFloor`) since a keyword-only or already-quality-
 * adjusted score isn't on the same scale as raw cosine similarity.
 */

function normalizeText(text: string): string {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

/** The custom disclosure taxonomy (Milestone 6) -- genuinely distinct
 * topics. Deliberately excludes the 7 broad Loughran-McDonald tone
 * categories (`positive`, `negative`, `uncertainty`, `litigious`,
 * `constraining`, `strong_modal`, `weak_modal`), which `RetrievalContext.
 * categories` also carries: real-corpus evaluation found that treating
 * those as coverage facets saturated the greedy selector's "new facet"
 * budget within the first 2-3 candidates (almost every substantive
 * passage carries several LM tone categories), so every subsequent
 * candidate -- even a genuinely different, on-topic one -- registered as
 * "redundant" purely because the small tone-category space was already
 * exhausted, not because its content actually repeated anything selected
 * so far. See the Milestone 7B.1b final report. */
const CUSTOM_TAXONOMY_CATEGORIES = new Set(["risk", "financial_condition", "governance", "strategy"]);

/** Exported so `evaluation/qa-failure-attribution.ts`'s RERANKING_MISS vs
 * EVIDENCE_SELECTION_MISS classification uses the exact same examination
 * window this builder actually applies, rather than duplicating the
 * multiplier as a second, driftable magic number. */
export const EXAMINATION_WINDOW_MULTIPLIER = 4;

/** Milestone 7B.1c Phase 5: the narrow/broad distinction the direct-
 * responsiveness gate applies. `corpus_wide` already covers both
 * deliberately unscoped questions (no ticker at all) and explicit
 * multi-company comparisons (`classifyScope` in `query-analysis.ts` falls
 * through to `corpus_wide` whenever more than one ticker is named) -- the
 * exact two "broad" shapes the milestone calls out (`broad_corpus_wide`,
 * `multi_company`), so no separate case-type signal is needed at runtime.
 * Exported for `groundedness-gate.ts`'s Phase 9 use of the same rule. */
export function isNarrowQuestion(analysis: QueryAnalysis): boolean {
  return analysis.requestedScope !== "corpus_wide";
}

function isBelowRelevanceFloor(candidate: RerankedEvidenceCandidate, minimumSemanticSimilarity: number): boolean {
  const isSemanticOnly = candidate.sources.length === 1 && candidate.sources[0] === "semantic";
  return isSemanticOnly && candidate.semanticRawSimilarity !== null && candidate.semanticRawSimilarity < minimumSemanticSimilarity;
}

function isInScope(candidate: RerankedEvidenceCandidate, analysis: QueryAnalysis): boolean {
  if (analysis.requiredTicker && candidate.context.companyTicker !== analysis.requiredTicker) return false;
  if (analysis.requiredReportSide && candidate.context.reportSide !== analysis.requiredReportSide) return false;
  if (analysis.requiredCategory && !candidate.context.categories.includes(analysis.requiredCategory)) return false;
  return true;
}

/**
 * Alignment status is deliberately only tracked as a "facet" when the
 * question itself asked about alignment changes (`analysis.alignmentStatuses`
 * non-empty) -- never as a general-purpose diversity dimension. Real-corpus
 * evaluation found that treating every alignment status as coverage-worthy
 * made the greedy selector actively seek out a `NEW`-status item and a
 * `REMOVED`-status item together purely to "cover more facets," which then
 * tripped `coherence-checker.ts`'s mixed-NEW+REMOVED-without-explanation
 * check on the large majority of multi-item selections (most real passages
 * carry a non-UNCHANGED alignment status) -- a false-positive contradiction
 * manufactured by the selector itself, not a genuine property of the
 * evidence. See the Milestone 7B.1b final report.
 */
function candidateFacets(candidate: RerankedEvidenceCandidate, analysis: QueryAnalysis): Set<string> {
  const facets = new Set<string>();
  for (const category of candidate.context.categories) {
    if (CUSTOM_TAXONOMY_CATEGORIES.has(category)) facets.add(`category:${category}`);
  }
  for (const subcategory of candidate.context.riskSubcategories) facets.add(`subcategory:${subcategory}`);
  if (candidate.context.reportSide) facets.add(`side:${candidate.context.reportSide}`);
  if (candidate.context.alignmentStatus && analysis.alignmentStatuses.includes(candidate.context.alignmentStatus)) {
    facets.add(`alignment:${candidate.context.alignmentStatus}`);
  }
  return facets;
}

function requiredFacetsFor(analysis: QueryAnalysis): string[] {
  const required = new Set<string>();
  if (analysis.requiredCategory) required.add(`category:${analysis.requiredCategory}`);
  for (const subcategory of analysis.subcategories) required.add(`subcategory:${subcategory}`);
  if (analysis.questionType === "comparative" || analysis.requestedReportSides.length === 2) {
    required.add("side:EARLIER");
    required.add("side:LATER");
  } else if (analysis.requiredReportSide) {
    required.add(`side:${analysis.requiredReportSide}`);
  }
  for (const status of analysis.alignmentStatuses) required.add(`alignment:${status}`);
  return [...required];
}

export function buildEvidenceSet(candidates: readonly RerankedEvidenceCandidate[], analysis: QueryAnalysis, config: QaConfig): EvidenceSet {
  const ordered = [...candidates].sort((a, b) => a.relevanceRank - b.relevanceRank);
  const rejected: EvidenceRejection[] = [];

  // 1. Dedup: by passage id, then by near-duplicate normalized text.
  const seenPassageIds = new Set<string>();
  const seenTextKeys = new Set<string>();
  const deduped: RerankedEvidenceCandidate[] = [];
  for (const candidate of ordered) {
    const textKey = normalizeText(candidate.context.text);
    if (seenPassageIds.has(candidate.passageId) || seenTextKeys.has(textKey)) {
      rejected.push({ candidateId: candidate.candidateId, passageId: candidate.passageId, retrievalContextId: candidate.retrievalContextId, reason: "DUPLICATE" });
      continue;
    }
    seenPassageIds.add(candidate.passageId);
    seenTextKeys.add(textKey);
    deduped.push(candidate);
  }

  // 2. Relevance floor.
  const minimumSemanticSimilarity = getRetrievalConfig().minimumSemanticSimilarity;
  const aboveFloor: RerankedEvidenceCandidate[] = [];
  for (const candidate of deduped) {
    if (isBelowRelevanceFloor(candidate, minimumSemanticSimilarity)) {
      rejected.push({ candidateId: candidate.candidateId, passageId: candidate.passageId, retrievalContextId: candidate.retrievalContextId, reason: "BELOW_RELEVANCE_FLOOR" });
      continue;
    }
    aboveFloor.push(candidate);
  }

  // 3. Scope split.
  const inScopeAll: RerankedEvidenceCandidate[] = [];
  for (const candidate of aboveFloor) {
    if (isInScope(candidate, analysis)) {
      inScopeAll.push(candidate);
    } else {
      rejected.push({ candidateId: candidate.candidateId, passageId: candidate.passageId, retrievalContextId: candidate.retrievalContextId, reason: "OUT_OF_SCOPE" });
    }
  }

  // 3b. Milestone 7B.1c Phase 5: narrow-question direct-responsiveness
  // gate. Broad/corpus-wide questions (`isNarrowQuestion` false) keep the
  // pre-7B.1c diversity-driven selection entirely -- a right-company/
  // wrong-topic passage must fail for a narrow question, but a broad
  // question's value comes precisely from covering many genuinely-relevant
  // angles, so it is never required to clear the full eligibility bar.
  const inScope: RerankedEvidenceCandidate[] = [];
  if (isNarrowQuestion(analysis)) {
    for (const candidate of inScopeAll) {
      if (candidate.evidenceEligible) {
        inScope.push(candidate);
      } else {
        rejected.push({ candidateId: candidate.candidateId, passageId: candidate.passageId, retrievalContextId: candidate.retrievalContextId, reason: "NOT_DIRECTLY_RESPONSIVE" });
      }
    }
  } else {
    inScope.push(...inScopeAll);
  }

  // 4. Greedy coverage-driven selection. Bounded to a fixed multiple of
  // `maxEvidenceSetSize` candidates *examined* (selected or rejected-as-
  // redundant combined) -- without this bound, `EVIDENCE_REDUNDANT`'s
  // denominator would scale with the full in-scope candidate pool (up to
  // ~40), and since the facet space (4 categories + subcategories + side)
  // is small relative to that pool, nearly every pool this size exhausts
  // its facets within the first handful of picks regardless of whether the
  // *selected* evidence is genuinely redundant -- inflating the ratio for
  // reasons unrelated to the actual evidence quality. Candidates beyond the
  // window are simply never examined (neither selected nor counted as
  // redundant), not silently rejected. See the Milestone 7B.1b final report.
  const REDUNDANCY_EXAMINATION_WINDOW_MULTIPLIER = EXAMINATION_WINDOW_MULTIPLIER;
  const examinationLimit = config.maxEvidenceSetSize * REDUNDANCY_EXAMINATION_WINDOW_MULTIPLIER;
  const selected: SelectedEvidence[] = [];
  const coveredFacets = new Set<string>();
  let examined = 0;
  for (const candidate of inScope) {
    if (selected.length >= config.maxEvidenceSetSize) break;
    if (examined >= examinationLimit) break;
    examined += 1;
    const facets = candidateFacets(candidate, analysis);
    const newFacets = [...facets].filter((facet) => !coveredFacets.has(facet));
    if (newFacets.length > 0 || selected.length < 2) {
      selected.push({ ...candidate, selectionOrder: selected.length + 1, newFacetsCovered: newFacets });
      for (const facet of newFacets) coveredFacets.add(facet);
    } else {
      rejected.push({ candidateId: candidate.candidateId, passageId: candidate.passageId, retrievalContextId: candidate.retrievalContextId, reason: "REDUNDANT_NO_NEW_COVERAGE" });
    }
  }

  const requiredFacets = requiredFacetsFor(analysis);
  const coveredRequiredFacets = requiredFacets.filter((facet) => coveredFacets.has(facet));
  const coverage: EvidenceCoverage = {
    requiredFacets,
    coveredFacets: [...coveredFacets],
    coverageRatio: requiredFacets.length > 0 ? coveredRequiredFacets.length / requiredFacets.length : 1,
  };

  return { selected, rejected, coverage };
}
