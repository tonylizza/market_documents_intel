/**
 * Track 7F.9 -- a NEW / REMOVED / SUBSTANTIALLY_MODIFIED status is only as
 * reliable as the alignment behind it: 7F.8 found moved passages
 * misclassified as NEW/REMOVED when alignment confidence was weak. Such
 * passages are labelled as possibly moved or restructured and are never
 * presented as a definitive explanation of a change.
 */
const CHANGE_STATUSES = new Set(["NEW", "REMOVED", "SUBSTANTIALLY_MODIFIED"]);
const WEAK_CONFIDENCES = new Set(["LOW", "NEEDS_REVIEW"]);

export const POSSIBLY_MOVED_LABEL = "Possibly moved or restructured";

export function isWeakChangeAttribution(alignmentStatus: string | null, confidence: string | null): boolean {
  if (alignmentStatus === null || confidence === null) return false;
  return CHANGE_STATUSES.has(alignmentStatus) && WEAK_CONFIDENCES.has(confidence);
}

export function alignmentCaveat(alignmentStatus: string, confidence: string): string | null {
  return isWeakChangeAttribution(alignmentStatus, confidence)
    ? `${POSSIBLY_MOVED_LABEL}: alignment confidence is weak, so similar text may appear elsewhere in the other report.`
    : null;
}
