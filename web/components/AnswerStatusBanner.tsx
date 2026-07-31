import type { AnswerStatus } from "@/lib/domain/qa-answer";
import styles from "./AnswerStatusBanner.module.css";

export interface AnswerStatusBannerProps {
  status: AnswerStatus;
  unsupportedPortion: string | null;
  errorDetail: string | null;
}

/** Plain-language labels -- the raw status enum is never shown to an
 * ordinary user (mirrors `GateStatusBanner`'s existing discipline). */
const STATUS_LABELS: Record<AnswerStatus, string> = {
  ANSWERED: "Answered from the report excerpts below",
  PARTIALLY_ANSWERED: "Partially answered -- see what's missing below",
  INSUFFICIENT_EVIDENCE: "Not enough evidence to answer this question",
  AMBIGUOUS_OR_CONFLICTING: "The evidence is ambiguous or conflicting",
  PROVIDER_UNAVAILABLE: "The answer generator is temporarily unavailable",
};

const STATUS_TONE: Record<AnswerStatus, "answered" | "partial" | "insufficient" | "ambiguous" | "unavailable"> = {
  ANSWERED: "answered",
  PARTIALLY_ANSWERED: "partial",
  INSUFFICIENT_EVIDENCE: "insufficient",
  AMBIGUOUS_OR_CONFLICTING: "ambiguous",
  PROVIDER_UNAVAILABLE: "unavailable",
};

export function AnswerStatusBanner({ status, unsupportedPortion, errorDetail }: AnswerStatusBannerProps) {
  const tone = STATUS_TONE[status];
  return (
    <div className={`${styles.banner} ${styles[tone]}`} role="status" aria-live="polite">
      <p className={styles.statusLabel}>{STATUS_LABELS[status]}</p>
      {status === "PARTIALLY_ANSWERED" && unsupportedPortion && (
        <p className={styles.detail}>Not covered by the evidence: {unsupportedPortion}</p>
      )}
      {status === "PROVIDER_UNAVAILABLE" && (
        <p className={styles.detail}>
          The retrieved excerpts below are still shown -- they were not used to write an answer.
        </p>
      )}
      {status === "PROVIDER_UNAVAILABLE" && errorDetail && <p className={styles.detail}>{errorDetail}</p>}
    </div>
  );
}
