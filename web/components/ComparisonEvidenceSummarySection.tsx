import type { ComparisonEvidenceSummary } from "@/lib/domain/passage";
import { ALIGNMENT_STATUSES, formatAlignmentStatusLabel } from "@/lib/config/passage-vocabulary";
import { formatCount } from "@/lib/formatting/numbers";
import styles from "./ComparisonEvidenceSummarySection.module.css";

export interface ComparisonEvidenceSummaryProps {
  summary: ComparisonEvidenceSummary;
}

/** Evidence-count summary -- reads the same six-status counts already used
 * by the comparison page's `PassageCompositionSection`, never a second,
 * differently derived tally. */
export function ComparisonEvidenceSummarySection({ summary }: ComparisonEvidenceSummaryProps) {
  return (
    <div className={styles.grid}>
      {ALIGNMENT_STATUSES.map((status) => (
        <div className={styles.card} key={status}>
          <span className={styles.count}>{formatCount(summary.counts[status])}</span>
          <span className={styles.label}>{formatAlignmentStatusLabel(status)}</span>
        </div>
      ))}
      <div className={styles.card}>
        <span className={styles.count}>{formatCount(summary.totalCount)}</span>
        <span className={styles.label}>Total aligned passages</span>
      </div>
    </div>
  );
}
