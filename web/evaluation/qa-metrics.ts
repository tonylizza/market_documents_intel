/**
 * Milestone 7B.1b Q&A evidence-selection metrics -- pure functions over
 * ranked/selected id lists and ground-truth judgments, matching
 * `evaluation/metrics.ts`'s convention: no imports from `lib/repositories`
 * or `lib/services`, so this module is runnable in a plain unit test with
 * no database.
 */
import type { GateStatus } from "@/lib/domain/qa-evidence";
import type { QaAnswerabilityClass } from "./qa-dataset";

export function evidencePrecisionAtK(selected: readonly string[], relevant: ReadonlySet<string>, k: number): number {
  const top = selected.slice(0, k);
  if (top.length === 0) return 0;
  const hits = top.filter((id) => relevant.has(id)).length;
  return hits / top.length;
}

export function evidenceRecallAtK(selected: readonly string[], relevant: ReadonlySet<string>, k: number): number {
  if (relevant.size === 0) return 1;
  const top = new Set(selected.slice(0, k));
  let hits = 0;
  for (const id of relevant) if (top.has(id)) hits += 1;
  return hits / relevant.size;
}

/** True when `selected` (as a set) fully contains at least one of the
 * alternate minimum-sufficient-evidence sets -- the core "did the system
 * actually assemble a usable answer" signal, distinct from precision/recall
 * over a flattened relevant-id union. */
export function recoveredMinimumSufficientSet(selected: readonly string[], sufficientSets: readonly (readonly string[])[]): boolean {
  if (sufficientSets.length === 0) return false;
  const selectedSet = new Set(selected);
  return sufficientSets.some((set) => set.length > 0 && set.every((id) => selectedSet.has(id)));
}

export function meanOf(values: readonly number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function rateOf(flags: readonly boolean[]): number {
  return meanOf(flags.map((f) => (f ? 1 : 0)));
}

export interface AnswerabilityOutcome {
  caseId: string;
  expected: QaAnswerabilityClass;
  actual: GateStatus;
}

/** Fraction of INSUFFICIENT_EVIDENCE-expected cases where the gate
 * correctly abstained (also reported INSUFFICIENT_EVIDENCE). */
export function correctAbstentionRate(outcomes: readonly AnswerabilityOutcome[]): number {
  const noAnswerCases = outcomes.filter((o) => o.expected === "INSUFFICIENT_EVIDENCE");
  if (noAnswerCases.length === 0) return 1;
  return rateOf(noAnswerCases.map((o) => o.actual === "INSUFFICIENT_EVIDENCE"));
}

/** Primary safety metric: fraction of INSUFFICIENT_EVIDENCE-expected cases
 * where the gate nonetheless reported SUPPORTED -- a confidently-wrong
 * answer to a question the corpus cannot actually support. */
export function noAnswerFalseSupportRate(outcomes: readonly AnswerabilityOutcome[]): number {
  const noAnswerCases = outcomes.filter((o) => o.expected === "INSUFFICIENT_EVIDENCE");
  if (noAnswerCases.length === 0) return 0;
  return rateOf(noAnswerCases.map((o) => o.actual === "SUPPORTED"));
}

export function classificationAccuracyFor(outcomes: readonly AnswerabilityOutcome[], expectedClass: QaAnswerabilityClass): number {
  const matching = outcomes.filter((o) => o.expected === expectedClass);
  if (matching.length === 0) return 1;
  return rateOf(matching.map((o) => o.actual === expectedClass));
}

/** Fraction of answerable cases (a non-empty minimum-sufficient-evidence
 * set exists) where the system actually recovered it -- distinct from
 * classification accuracy, which only checks the gate *label*. */
export function answerableQuestionCoverage(recoveredFlags: readonly boolean[]): number {
  return rateOf(recoveredFlags);
}

export function unsupportedEvidenceRate(caseHasSelectedTrap: readonly boolean[]): number {
  return rateOf(caseHasSelectedTrap);
}

export function duplicateEvidenceRate(caseHasDuplicatePassageId: readonly boolean[]): number {
  return rateOf(caseHasDuplicatePassageId);
}

export function numericFragmentMisuseRate(caseSupportedBySoleFragment: readonly boolean[]): number {
  return rateOf(caseSupportedBySoleFragment);
}

export interface GroupedAccuracy {
  group: string;
  caseCount: number;
  accuracy: number;
}

export function accuracyByGroup(outcomes: readonly (AnswerabilityOutcome & { group: string })[]): GroupedAccuracy[] {
  const groups = new Map<string, (AnswerabilityOutcome & { group: string })[]>();
  for (const outcome of outcomes) {
    const list = groups.get(outcome.group) ?? [];
    list.push(outcome);
    groups.set(outcome.group, list);
  }
  return [...groups.entries()].map(([group, list]) => ({
    group,
    caseCount: list.length,
    accuracy: rateOf(list.map((o) => o.expected === o.actual)),
  }));
}

export function percentile(values: readonly number[], p: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length));
  return sorted[index];
}
