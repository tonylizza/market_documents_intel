import type { EvidenceCoherence, EvidenceSet, GateDecision, GateReasonCode, GateStatus, GroundednessSignals, QueryAnalysis, SelectedEvidence } from "@/lib/domain/qa-evidence";
import { getRetrievalConfig } from "@/lib/config/retrieval-config";
import { getGateStrategyConfig, type GateStrategyConfig, type QaConfig } from "@/lib/config/qa-config";
import { getConceptFamily, matchesFamily } from "@/lib/domain/concept-families";

/**
 * Milestone 7B.1b/7B.1c: the groundedness/sufficiency gate -- never a
 * single cosine-similarity threshold. Combines direct-responsiveness
 * eligibility (Phase 4), required concept coverage, query-type-specific
 * requirements, scope compliance, evidence-set coverage, coherence,
 * restatement handling, and comparison/chronology checks through a fixed
 * precedence table -- "which tier does this land in," never an opaque
 * if/else chain, and never one aggregate score.
 *
 * Precedence (extends the Milestone 7B.1b table): no evidence -> citation
 * incomplete -> weak raw retrieval strength -> all-fragment evidence ->
 * (Phase 9) no directly-responsive evidence -> (Phase 7/8, when
 * `restatementSafeguards` is enabled) restatement/comparison/chronology
 * ambiguity -> contradiction -> (Phase 6) subquestion-based
 * SUPPORTED/PARTIALLY_SUPPORTED. Each tier is checked in this fixed order
 * because a more specific, stronger finding (e.g. "no evidence at all")
 * must never be reported as a softer, later one (e.g. "conflicting").
 */

const KEYWORD_STRONG_RANK_WINDOW = 10;

function computeSignals(evidenceSet: EvidenceSet, analysis: QueryAnalysis, coherence: EvidenceCoherence, minimumSemanticSimilarity: number): GroundednessSignals {
  const { selected, rejected, coverage } = evidenceSet;
  const distinctPassageCount = new Set(selected.map((item) => item.passageId)).size;

  const isStrong = (item: (typeof selected)[number]): boolean =>
    (item.sources.includes("keyword") && item.lexicalRankPosition !== null && item.lexicalRankPosition <= KEYWORD_STRONG_RANK_WINDOW) ||
    (item.semanticRawSimilarity !== null && item.semanticRawSimilarity >= minimumSemanticSimilarity) ||
    // Milestone 7B.1d (experimental): a chunk-only candidate (no keyword/
    // semantic hit of its own) can still count as strong evidence if the
    // child chunk that surfaced it was itself a close cosine match -- same
    // threshold as the canonical semantic path, deliberately not a looser
    // one, so chunk-sourced evidence is never held to a lower bar.
    (item.sources.includes("chunk") && item.chunkSimilarity != null && item.chunkSimilarity >= minimumSemanticSimilarity);
  const strongEvidenceCount = selected.filter(isStrong).length;
  const directlyResponsiveCount = selected.filter((item) => item.evidenceEligible).length;

  const hasOutOfScopeRejections = rejected.some((r) => r.reason === "OUT_OF_SCOPE");
  const hasHardScopeRequirement = analysis.requiredTicker !== null || analysis.requiredCategory !== null;
  const requiredScopeSatisfied = distinctPassageCount > 0 || !(hasHardScopeRequirement && hasOutOfScopeRejections);
  const requiredSideSatisfied = distinctPassageCount > 0 || !(analysis.requiredReportSide !== null && hasOutOfScopeRejections);

  const citationComplete =
    selected.length === 0 ||
    selected.every(
      (item) =>
        Boolean(item.citation.passageId) &&
        Boolean(item.citation.reportId) &&
        Boolean(item.citation.retrievalContextId) &&
        item.citation.firstPageNumber != null &&
        item.citation.lastPageNumber != null,
    );

  const topicCoverageRatio = coverage.coverageRatio;

  const top = selected[0];
  let topScoreMargin = Number.POSITIVE_INFINITY;
  if (top && top.semanticAdjustedScore !== null) {
    topScoreMargin = top.semanticAdjustedScore - minimumSemanticSimilarity;
  }

  const redundantRejectionCount = rejected.filter((r) => r.reason === "REDUNDANT_NO_NEW_COVERAGE").length;
  const redundancyDenominator = selected.length + redundantRejectionCount;
  const redundancyRatio = redundancyDenominator > 0 ? redundantRejectionCount / redundancyDenominator : 0;

  const numericFragmentWithoutContextRatio =
    selected.length > 0 ? selected.filter((item) => item.numericFragmentSeverity === "fragment_without_context").length / selected.length : 0;

  return {
    distinctPassageCount,
    strongEvidenceCount,
    requiredScopeSatisfied,
    requiredSideSatisfied,
    citationComplete,
    topicCoverageRatio,
    topScoreMargin,
    numericFragmentWithoutContextRatio,
    redundancyRatio,
    contradictionDetected: coherence.hasContradiction,
    directlyResponsiveCount,
  };
}

/** Milestone 7B.1c Phase 6: is a single material element supported by the
 * selected, direct-responsiveness-eligible evidence? An element with no
 * resolved concept family (a generic/unresolved clause) falls back to
 * "any eligible evidence at all" -- the most permissive reading available,
 * since there's no more specific family to check against. */
function isElementSupported(element: { text: string; requiredFamilies: string[] }, selected: readonly SelectedEvidence[]): boolean {
  const eligible = selected.filter((item) => item.evidenceEligible);
  if (eligible.length === 0) return false;
  if (element.requiredFamilies.length === 0) return true;
  return eligible.some((item) => {
    const text = `${item.context.heading ?? ""} ${item.context.text}`;
    return element.requiredFamilies.some((id) => {
      const family = getConceptFamily(id);
      return family !== undefined && matchesFamily(family, text);
    });
  });
}

function elementsFor(analysis: QueryAnalysis): { text: string; requiredFamilies: string[] }[] {
  return analysis.materialElements.length > 0 ? analysis.materialElements : [{ text: analysis.normalizedQuestion, requiredFamilies: analysis.requiredConceptFamilies }];
}

function buildPartialSupportRationale(supported: string[], unsupported: string[], strict: boolean): string {
  if (unsupported.length === 0) return supported.length > 1 ? "All material elements of the question are directly supported by selected evidence." : "The question's single element is directly supported by selected evidence.";
  if (supported.length === 0) return "No material element of the question is directly supported by selected evidence.";
  if (!strict) return "Coverage/margin/redundancy signals were below threshold; subquestion-level separability was not evaluated under this configuration.";
  return `Supported: ${supported.join(" | ")}. Not supported: ${unsupported.join(" | ")}.`;
}

export function evaluateGroundedness(evidenceSet: EvidenceSet, analysis: QueryAnalysis, coherence: EvidenceCoherence, config: QaConfig): GateDecision {
  const strategy: GateStrategyConfig = getGateStrategyConfig(config);
  const minimumSemanticSimilarity = getRetrievalConfig().minimumSemanticSimilarity;
  const signals = computeSignals(evidenceSet, analysis, coherence, minimumSemanticSimilarity);
  const reasonCodes: GateReasonCode[] = [];
  let status: GateStatus;

  const elements = elementsFor(analysis);
  const supportedSubquestions = elements.filter((e) => isElementSupported(e, evidenceSet.selected)).map((e) => e.text);
  const unsupportedSubquestions = elements.filter((e) => !isElementSupported(e, evidenceSet.selected)).map((e) => e.text);

  if (signals.distinctPassageCount === 0) {
    if (analysis.unresolvedRequiredConcepts.length > 0) reasonCodes.push("REQUIRED_CONCEPT_MISSING");
    if (!signals.requiredScopeSatisfied) reasonCodes.push("REQUIRED_SCOPE_NOT_COVERED");
    if (!signals.requiredSideSatisfied) reasonCodes.push("MISSING_COMPARISON_SIDE");
    if (reasonCodes.length === 0) reasonCodes.push("NO_DIRECT_EVIDENCE");
    status = "INSUFFICIENT_EVIDENCE";
  } else if (!signals.citationComplete) {
    reasonCodes.push("CITATION_METADATA_INCOMPLETE");
    status = "INSUFFICIENT_EVIDENCE";
  } else if (signals.strongEvidenceCount === 0) {
    reasonCodes.push("ONLY_WEAK_INDIRECT_EVIDENCE");
    status = "INSUFFICIENT_EVIDENCE";
  } else if (signals.numericFragmentWithoutContextRatio === 1) {
    reasonCodes.push("NUMERIC_FRAGMENT_WITHOUT_CONTEXT");
    status = "INSUFFICIENT_EVIDENCE";
  } else if (strategy.applyGenericPenalty && signals.directlyResponsiveCount === 0) {
    // Milestone 7B.1c Phase 9: right-company/right-scope but wrong-topic
    // evidence -- the gate's core new defense against confusing topic/
    // company resemblance with direct responsiveness.
    const reasons = new Set(evidenceSet.selected.flatMap((item) => item.ineligibilityReasons));
    if (reasons.has("COMPANY_ONLY_MATCH")) reasonCodes.push("COMPANY_ONLY_MATCH", "WRONG_TOPIC_RIGHT_COMPANY");
    else if (reasons.has("SCOPE_ONLY_MATCH")) reasonCodes.push("SCOPE_ONLY_MATCH");
    else if (reasons.has("GENERIC_ONLY_MATCH")) reasonCodes.push("GENERIC_ONLY_MATCH");
    else reasonCodes.push("DIRECT_RESPONSIVENESS_BELOW_FLOOR");
    status = "INSUFFICIENT_EVIDENCE";
  } else if (strategy.restatementSafeguards && coherence.restatementAmbiguityDetected) {
    reasonCodes.push("RESTATEMENT_DETECTED", "RESTATEMENT_AMBIGUITY", coherence.restatementChronologyClear ? "RESTATEMENT_CHRONOLOGY_CLEAR" : "RESTATEMENT_CHRONOLOGY_AMBIGUOUS");
    status = "AMBIGUOUS_OR_CONFLICTING";
  } else if (strategy.restatementSafeguards && analysis.questionType === "comparative" && coherence.comparisonContextSatisfied === false) {
    // Milestone 7B.1c Phase 8: distinguish a side that's wholly absent from
    // selected evidence (COMPARISON_CONTEXT_MISSING) from a side that's
    // present but not topically responsive (COMPARISON_TOPIC_MISMATCH) --
    // both fail `comparisonContextSatisfied`, but they're different findings.
    const earlierPresent = evidenceSet.selected.some((item) => item.context.reportSide === "EARLIER");
    const laterPresent = evidenceSet.selected.some((item) => item.context.reportSide === "LATER");
    reasonCodes.push(earlierPresent && laterPresent ? "COMPARISON_TOPIC_MISMATCH" : "COMPARISON_CONTEXT_MISSING");
    if (!earlierPresent || !laterPresent) reasonCodes.push("REPORT_SIDE_MISMATCH");
    status = "AMBIGUOUS_OR_CONFLICTING";
  } else if (strategy.restatementSafeguards && analysis.questionType === "chronological" && coherence.dateRangeCovered === false) {
    reasonCodes.push("DATE_RANGE_NOT_COVERED", "CHRONOLOGY_INCOMPLETE");
    status = "INSUFFICIENT_EVIDENCE";
  } else if (signals.contradictionDetected) {
    reasonCodes.push("CONFLICTING_EVIDENCE");
    status = "AMBIGUOUS_OR_CONFLICTING";
  } else if (strategy.strictPartialSupport && elements.length >= 2) {
    // Milestone 7B.1c Phase 6: strict, separable-elements PARTIALLY_SUPPORTED.
    if (unsupportedSubquestions.length === 0) {
      reasonCodes.push(signals.distinctPassageCount === 1 ? "SUPPORTED_BY_SINGLE_PASSAGE" : "SUPPORTED_BY_MULTIPLE_PASSAGES");
      status = "SUPPORTED";
    } else if (supportedSubquestions.length > 0) {
      reasonCodes.push("INSUFFICIENT_TOPIC_COVERAGE");
      status = "PARTIALLY_SUPPORTED";
    } else {
      reasonCodes.push("INSUFFICIENT_TOPIC_COVERAGE");
      status = "INSUFFICIENT_EVIDENCE";
    }
  } else {
    // Pre-7B.1c behavior (or strict mode on a single-element question,
    // where "partial" would mean "vaguely related," which the milestone
    // explicitly forbids -- PARTIAL_SUPPORT_NOT_SEPARABLE routes it back to
    // an ordinary SUPPORTED/INSUFFICIENT_EVIDENCE decision instead).
    if (strategy.strictPartialSupport) reasonCodes.push("PARTIAL_SUPPORT_NOT_SEPARABLE");
    if (signals.topicCoverageRatio < config.minTopicCoverageRatio) reasonCodes.push("INSUFFICIENT_TOPIC_COVERAGE");
    if (signals.topScoreMargin < config.minRelevanceMargin) reasonCodes.push("LOW_RELEVANCE_MARGIN");
    if (signals.redundancyRatio > config.maxRedundancyRatio) reasonCodes.push("EVIDENCE_REDUNDANT");
    if (signals.numericFragmentWithoutContextRatio > 0 && signals.numericFragmentWithoutContextRatio < 1) {
      reasonCodes.push("NUMERIC_FRAGMENT_WITHOUT_CONTEXT");
    }

    const softReasonCount = reasonCodes.filter((code) => code !== "PARTIAL_SUPPORT_NOT_SEPARABLE").length;
    if (strategy.strictPartialSupport) {
      // Separability was already unavailable (single element) -- never
      // PARTIALLY_SUPPORTED here; either fully supported or insufficient.
      status = softReasonCount === 0 ? "SUPPORTED" : "INSUFFICIENT_EVIDENCE";
      if (status === "SUPPORTED") reasonCodes.push(signals.distinctPassageCount === 1 ? "SUPPORTED_BY_SINGLE_PASSAGE" : "SUPPORTED_BY_MULTIPLE_PASSAGES");
    } else if (softReasonCount > 0) {
      status = "PARTIALLY_SUPPORTED";
    } else {
      reasonCodes.push(signals.distinctPassageCount === 1 ? "SUPPORTED_BY_SINGLE_PASSAGE" : "SUPPORTED_BY_MULTIPLE_PASSAGES");
      status = "SUPPORTED";
    }
  }

  // Milestone 7B.1c Phase 8: an informational append, never a status
  // driver -- "increased"/"decreased" direction claims have no stored
  // verification signal (see `qa-evidence.ts`'s `ComparisonDirection` doc),
  // so any non-abstaining status built partly on that lexical direction
  // must carry an explicit "not verified" warning. `added`/`removed`
  // claims are exempt -- those are reliably derived from `alignmentStatus`.
  const hasUnverifiableDirection = analysis.directionalConcepts.some((d) => d === "increased" || d === "decreased");
  if (strategy.restatementSafeguards && hasUnverifiableDirection && (status === "SUPPORTED" || status === "PARTIALLY_SUPPORTED")) {
    reasonCodes.push("DIRECTION_NOT_VERIFIED");
  }

  // Milestone 7B.1c Phase 7: restatement chronology *was* clear (both
  // original and restated context selected, unambiguously ordered) --
  // informational, since the ambiguous case already routed to
  // AMBIGUOUS_OR_CONFLICTING above and never reaches here.
  if (strategy.restatementSafeguards && coherence.restatementChronologyClear === true && (status === "SUPPORTED" || status === "PARTIALLY_SUPPORTED")) {
    reasonCodes.push("ORIGINAL_AND_RESTATED_VALUES_PRESENT", "RESTATEMENT_CHRONOLOGY_CLEAR");
    if (coherence.supersededPassageIds.length > 0) reasonCodes.push("SUPERSEDED_EVIDENCE", "CORRECTION_CONTEXT_REQUIRED");
  }

  return {
    status,
    reasonCodes,
    signals,
    supportedSubquestions,
    unsupportedSubquestions,
    partialSupportRationale: buildPartialSupportRationale(supportedSubquestions, unsupportedSubquestions, strategy.strictPartialSupport),
  };
}
