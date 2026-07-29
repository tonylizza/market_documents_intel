import type { RawQuality } from "@/lib/domain/quality";
import { QualityBadge } from "./QualityBadge";
import { Tooltip } from "./Tooltip";
import styles from "./DisclosureChangeSummary.module.css";

export interface DisclosureChangeSummaryProps {
  score: number | null;
  label: string | null;
  quality: RawQuality | null;
  qualityLabel: string | null;
}

/**
 * Overall disclosure-change magnitude + its quality, always shown
 * together. A review-qualified (NEEDS_REVIEW) value is genuinely
 * displayed -- this component never hides it and never renders it any
 * differently based on primary eligibility, since eligibility governs
 * *discovery ranking* placement, not whether the value itself is shown.
 * `null` score renders a plain "not available" state instead of a
 * fabricated zero.
 */
export function DisclosureChangeSummary({ score, label, quality, qualityLabel }: DisclosureChangeSummaryProps) {
  return (
    <div className={styles.wrapper}>
      <div className={styles.headingRow}>
        <span className={styles.heading}>Overall disclosure change</span>
        <Tooltip content="This magnitude is relative to the reports currently published in this corpus. It carries the quality label shown below and is not used as a primary ranking signal until independently confirmed.">
          <span aria-hidden="true">?</span>
        </Tooltip>
      </div>
      {score === null ? (
        <span className={styles.unavailable}>Not available for this comparison</span>
      ) : (
        <span className={styles.magnitude}>{label ?? "Change detected"}</span>
      )}
      <QualityBadge dimension="disclosure-change" quality={quality} label={qualityLabel} compact />
    </div>
  );
}
