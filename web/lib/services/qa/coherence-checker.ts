import type { EvidenceCoherence, EvidenceRejection, QueryAnalysis, SelectedEvidence } from "@/lib/domain/qa-evidence";
import type { RetrievalContext } from "@/lib/domain/retrieval";
import { isRestatementFlagged, restatementChronologyIsClear, findSupersededPassageIds } from "@/lib/services/qa/restatement-detection";

/**
 * Milestone 7B.1b: bounded coherence/contradiction checks over an already-
 * constructed evidence set. Deliberately conservative -- when a check can't
 * confidently establish coherence, it flags ambiguity rather than assuming
 * everything agrees (milestone: "prefer AMBIGUOUS_OR_CONFLICTING over
 * pretending the evidence is coherent").
 */

const EXPLANATORY_LINK_PATTERN = /\b(replaced|reclassified|moved to|superseded|renamed|relocated|consolidated into)\b/i;

function evidencePeriod(context: RetrievalContext): string | null {
  return context.reportPeriodEnd ?? context.laterPeriodEnd ?? context.earlierPeriodEnd;
}

/** A question is only expected to resolve to a single report period when it
 * *itself* narrows to one -- an explicit date range, or scope narrowed to
 * one specific comparison. An open-ended descriptive question ("what
 * growth opportunities has ACT identified") has no inherent period scope:
 * the same theme recurring across several years' reports is breadth, not
 * contradiction. Real-corpus evaluation found the previous, broader
 * heuristic (anything non-comparative/non-chronological) flagged the large
 * majority of ordinary descriptive questions as "conflicting" merely
 * because ACT's 9 report comparisons span 2016-2024 and relevant content
 * exists in more than one of them -- a false-positive contradiction
 * manufactured by an over-eager period check, not a real disagreement in
 * the evidence. See the Milestone 7B.1b final report. */
function expectsSinglePeriod(analysis: QueryAnalysis): boolean {
  return analysis.requestedScope === "single_comparison" || analysis.dateRange !== null;
}

export function checkCoherence(
  selected: readonly SelectedEvidence[],
  rejected: readonly EvidenceRejection[],
  analysis: QueryAnalysis,
): EvidenceCoherence {
  const distinctPeriods = new Set(
    selected.map((item) => evidencePeriod(item.context)).filter((period): period is string => period !== null),
  );
  const conflictingPeriods = expectsSinglePeriod(analysis) && distinctPeriods.size > 1;

  const hasNew = selected.some((item) => item.context.alignmentStatus === "NEW");
  const hasRemoved = selected.some((item) => item.context.alignmentStatus === "REMOVED");
  const hasExplanatoryLink = selected.some((item) => EXPLANATORY_LINK_PATTERN.test(item.context.text));
  const mixedAlignmentWithoutExplanation = hasNew && hasRemoved && !hasExplanatoryLink;

  // Scoped to duplicates whose *kept* counterpart is actually in the final
  // selected set -- a duplicate rejected far down the candidate list that
  // never had any chance of being double-counted isn't a coherence concern.
  // This is diagnostic (confirms dedup correctly prevented the same
  // disclosure from posing as two independent sources) -- it feeds
  // `EVIDENCE_REDUNDANT` territory, not `CONFLICTING_EVIDENCE`, so it is
  // deliberately *not* included in `hasContradiction` below.
  const selectedPassageIds = new Set(selected.map((item) => item.passageId));
  const duplicateCountedAsIndependent = rejected.some(
    (rejection) => rejection.reason === "DUPLICATE" && selectedPassageIds.has(rejection.passageId),
  );

  const outOfRangeEvidence = selected.some((item) => {
    if (analysis.dateRange) {
      const period = evidencePeriod(item.context);
      if (period && (period < analysis.dateRange.start! || period > analysis.dateRange.end!)) return true;
    }
    if (analysis.tickers.length > 0 && !analysis.tickers.includes(item.context.companyTicker)) return true;
    return false;
  });

  // Milestone 7B.1c Phase 7: restatement/correction ambiguity.
  const flaggedItems = selected.filter(isRestatementFlagged);
  const restatementSignalPresent = flaggedItems.length > 0 || analysis.ambiguitySensitiveConcepts.length > 0;
  const restatementChronologyClear = restatementSignalPresent ? (flaggedItems.length >= 2 ? restatementChronologyIsClear(flaggedItems) : flaggedItems.length === 1 ? flaggedItems[0].context.reportSide !== null : false) : null;
  const restatementAmbiguityDetected = restatementSignalPresent && restatementChronologyClear === false;
  const supersededPassageIds = findSupersededPassageIds(selected);

  // Milestone 7B.1c Phase 8: comparative/chronological safeguards.
  let comparisonContextSatisfied: boolean | null = null;
  if (analysis.questionType === "comparative" || analysis.requestedReportSides.length === 2) {
    const earlier = selected.filter((item) => item.context.reportSide === "EARLIER" && item.evidenceEligible);
    const later = selected.filter((item) => item.context.reportSide === "LATER" && item.evidenceEligible);
    comparisonContextSatisfied = earlier.length > 0 && later.length > 0;
  }

  let dateRangeCovered: boolean | null = null;
  if (analysis.dateRange) {
    dateRangeCovered = selected.some((item) => {
      const period = evidencePeriod(item.context);
      return period !== null && period >= analysis.dateRange!.start! && period <= analysis.dateRange!.end!;
    });
  }

  return {
    conflictingPeriods,
    mixedAlignmentWithoutExplanation,
    duplicateCountedAsIndependent,
    outOfRangeEvidence,
    hasContradiction: conflictingPeriods || mixedAlignmentWithoutExplanation,
    restatementAmbiguityDetected,
    restatementChronologyClear,
    supersededPassageIds,
    comparisonContextSatisfied,
    dateRangeCovered,
  };
}
