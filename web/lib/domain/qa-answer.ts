import type { QaEvidenceChunk } from "@/lib/domain/qa-chunk";

/**
 * Milestone 7B.2 answer-status vocabulary. `PROVIDER_UNAVAILABLE` is set
 * only by our own code (a generation-provider call that failed/timed out
 * after its bounded retry) -- the model itself never returns that value.
 */
export type AnswerStatus =
  | "ANSWERED"
  | "PARTIALLY_ANSWERED"
  | "INSUFFICIENT_EVIDENCE"
  | "AMBIGUOUS_OR_CONFLICTING"
  | "PROVIDER_UNAVAILABLE";

export const ANSWER_STATUSES: readonly AnswerStatus[] = [
  "ANSWERED",
  "PARTIALLY_ANSWERED",
  "INSUFFICIENT_EVIDENCE",
  "AMBIGUOUS_OR_CONFLICTING",
  "PROVIDER_UNAVAILABLE",
];

/** The generation model's raw structured output, before it is combined with
 * retrieval evidence into a `QaAnswer`. */
export interface GeneratedAnswer {
  status: Exclude<AnswerStatus, "PROVIDER_UNAVAILABLE">;
  answerText: string;
  /** Chunk ids the model asserts it cited -- verified against the actual
   * evidence set by the caller (`verifyCitedChunkIds`), never trusted
   * blindly, since a fabricated chunk id would otherwise silently produce a
   * broken citation link. */
  citedChunkIds: string[];
  /** Present only for `PARTIALLY_ANSWERED` -- an explicit statement of what
   * the evidence does NOT support (brief: "Allow a partial answer only when
   * the supported and unsupported portions are explicit"). */
  unsupportedPortion: string | null;
}

/** The final, citation-verified answer returned to `/ask`. */
export interface QaAnswer {
  status: AnswerStatus;
  answerText: string | null;
  unsupportedPortion: string | null;
  /** Evidence actually cited by the model, in the order retrieval returned
   * them -- a subset of the full evidence set the model was shown. */
  citedEvidence: QaEvidenceChunk[];
  /** The full retrieved (deduplicated) evidence set, always returned even
   * on `INSUFFICIENT_EVIDENCE`/`PROVIDER_UNAVAILABLE` so `/ask` can still
   * show inspectable excerpts (brief: "return the retrieved excerpts and
   * citations" on provider failure). */
  allEvidence: QaEvidenceChunk[];
  providerLatencyMs: number | null;
  errorDetail: string | null;
}
