import type { SelectedEvidence } from "@/lib/domain/qa-evidence";
import { matchesRestatementTerms } from "@/lib/domain/concept-families";

/**
 * Milestone 7B.1c Phase 7: restatement/correction signal detection over
 * already-selected evidence. A passage is restatement-flagged when it
 * either uses the milestone's restatement vocabulary directly, or the
 * alignment pipeline itself couldn't confidently classify it
 * (`alignmentStatus === "AMBIGUOUS"` -- Milestone 6's own uncertainty
 * signal, reused rather than re-derived).
 */
const EXPLANATORY_LINK_PATTERN = /\b(replaced|reclassified|moved to|superseded|renamed|relocated|consolidated into|restated|corrected)\b/i;

export function isRestatementFlagged(item: SelectedEvidence): boolean {
  const text = `${item.context.heading ?? ""} ${item.context.text}`;
  return matchesRestatementTerms(text) || item.context.alignmentStatus === "AMBIGUOUS";
}

export function hasExplanatoryLink(item: SelectedEvidence): boolean {
  return EXPLANATORY_LINK_PATTERN.test(item.context.text);
}

/** Chronology is "clear" for a pair of restatement-flagged items only when
 * they carry different, explicit report sides (EARLIER vs LATER) -- two
 * restatement-flagged items on the *same* side, or with a null side, gives
 * no way to tell which value is current. */
export function restatementChronologyIsClear(items: readonly SelectedEvidence[]): boolean {
  const sides = new Set(items.map((item) => item.context.reportSide).filter((side): side is NonNullable<typeof side> => side !== null));
  return items.length > 0 && sides.size === items.length && sides.size >= 2;
}

/** A restatement-flagged item is superseded when a *later-side* selected
 * item explicitly links back to it (the existing `EXPLANATORY_LINK_PATTERN`
 * vocabulary already used by `coherence-checker.ts`). Reports only --
 * never excludes the superseded item from the evidence set. */
export function findSupersededPassageIds(items: readonly SelectedEvidence[]): string[] {
  const flagged = items.filter(isRestatementFlagged);
  if (flagged.length < 2) return [];
  const later = flagged.filter((item) => item.context.reportSide === "LATER" && hasExplanatoryLink(item));
  if (later.length === 0) return [];
  return flagged.filter((item) => item.context.reportSide === "EARLIER").map((item) => item.passageId);
}
