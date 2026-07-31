/**
 * Milestone 7B.1c Phase 1: deterministic failure-stage classification for
 * the 74-case Q&A evaluation dataset. Pure functions over already-computed
 * pipeline output (candidate ids, reranked ranks, final selection, gate
 * status) -- no database, no re-running the pipeline -- so this module is
 * unit-testable with small synthetic fixtures, matching `qa-metrics.ts`'s
 * convention.
 *
 * `GROUND_TRUTH_AMBIGUITY` is deliberately never returned by
 * `classifyFailureStage` -- the milestone requires it be a human judgment
 * ("the expected set is incomplete, overly narrow, or genuinely
 * ambiguous"), applied as a manual override by the runner script after
 * reviewing results, not an automatic inference.
 */
import type { GateStatus } from "@/lib/domain/qa-evidence";
import type { QaAnswerabilityClass } from "./qa-dataset";

export type FailureStage =
  | "RETRIEVAL_MISS"
  | "RERANKING_MISS"
  | "EVIDENCE_SELECTION_MISS"
  | "GATE_MISCLASSIFICATION"
  | "GROUND_TRUTH_AMBIGUITY"
  | "PIPELINE_SUCCESS";

export interface SufficientSetProbe {
  /** Every id in the alternate set appears somewhere in the merged
   * (pre-rerank) candidate pool. */
  present: boolean;
  /** Every id in the alternate set was ranked inside the evidence-set
   * builder's examination window (present AND reachable). */
  inWindow: boolean;
  /** Best (lowest) post-rerank rank among the set's ids that were present
   * at all -- `null` when none were present. Reporting-only. */
  bestRank: number | null;
}

export function probeSufficientSet(
  set: readonly string[],
  candidatePassageIds: ReadonlySet<string>,
  rankByPassageId: ReadonlyMap<string, number>,
  examinationWindow: number,
): SufficientSetProbe {
  if (set.length === 0) return { present: false, inWindow: false, bestRank: null };
  const present = set.every((id) => candidatePassageIds.has(id));
  const ranks = set.map((id) => rankByPassageId.get(id)).filter((r): r is number => r !== undefined);
  const bestRank = ranks.length > 0 ? Math.min(...ranks) : null;
  const inWindow = present && set.every((id) => {
    const rank = rankByPassageId.get(id);
    return rank !== undefined && rank <= examinationWindow;
  });
  return { present, inWindow, bestRank };
}

export interface ClassifyFailureStageInput {
  expected: QaAnswerabilityClass;
  actual: GateStatus;
  sufficientSets: readonly (readonly string[])[];
  setProbes: readonly SufficientSetProbe[];
  /** Whether the final *selected* evidence recovered at least one full
   * alternate sufficient set (`recoveredMinimumSufficientSet`). */
  recovered: boolean;
}

/**
 * Stage definitions (see the milestone plan):
 * - RETRIEVAL_MISS: required evidence absent from merged candidates.
 * - RERANKING_MISS: present but below the effective selection window.
 * - EVIDENCE_SELECTION_MISS: ranks high enough but is not selected.
 * - GATE_MISCLASSIFICATION: selected evidence and final status disagree
 *   with ground truth (including no-answer cases where nothing needed to
 *   be selected but the gate status itself is wrong).
 * - PIPELINE_SUCCESS: correct evidence and correct status.
 *
 * Precedence: a no-answer-expected case (empty `sufficientSets`) skips
 * straight to a status comparison -- there is no "required evidence" to
 * probe for. An answerable case walks retrieval -> reranking -> selection
 * -> gate in that order, stopping at the first stage that didn't clear.
 */
export function classifyFailureStage(input: ClassifyFailureStageInput): FailureStage {
  if (input.sufficientSets.length === 0) {
    return input.actual === input.expected ? "PIPELINE_SUCCESS" : "GATE_MISCLASSIFICATION";
  }
  if (!input.setProbes.some((p) => p.present)) return "RETRIEVAL_MISS";
  if (!input.setProbes.some((p) => p.inWindow)) return "RERANKING_MISS";
  if (!input.recovered) return "EVIDENCE_SELECTION_MISS";
  return input.actual === input.expected ? "PIPELINE_SUCCESS" : "GATE_MISCLASSIFICATION";
}
