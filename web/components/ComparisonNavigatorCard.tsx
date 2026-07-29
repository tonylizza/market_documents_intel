import Link from "next/link";
import type { ComparisonSummary } from "@/lib/domain/comparison";
import { formatComparisonPeriod } from "@/lib/formatting/dates";
import { QualityBadge } from "./QualityBadge";
import styles from "./ComparisonNavigatorCard.module.css";

export interface ComparisonNavigatorCardProps {
  comparison: ComparisonSummary;
  companyTicker: string;
  selected: boolean;
}

/**
 * One navigator entry -- a real link (`/companies/[ticker]?comparison=...`)
 * so the navigator works with JavaScript disabled and stays a genuine,
 * shareable, back-button-friendly URL, not a client-only state toggle.
 * Every field required by the milestone brief's "comparison card content"
 * list is rendered here; `Review recommended` is never hidden inside a
 * collapsed/technical section.
 */
export function ComparisonNavigatorCard({ comparison, companyTicker, selected }: ComparisonNavigatorCardProps) {
  const period = formatComparisonPeriod(comparison.earlierPeriodEnd, comparison.laterPeriodEnd);

  return (
    <Link
      href={`/companies/${companyTicker}?comparison=${comparison.id}`}
      className={`${styles.card} ${selected ? styles.selected : ""}`}
      aria-current={selected ? "true" : undefined}
      data-comparison-id={comparison.id}
    >
      <div className={styles.periodRow}>
        <span className={styles.period}>{period ?? "Period unavailable"}</span>
        {comparison.isHistoricalPeakChange && <span className={styles.peakFlag}>Historical peak change</span>}
      </div>

      {comparison.isTransition && <p className={styles.flag}>Transition report</p>}
      {comparison.isIrregularGap && <p className={styles.flag}>Irregular reporting gap ({comparison.gapMonths} mo)</p>}

      <div className={styles.magnitudeRow}>
        <span className={styles.magnitudeLabel}>Disclosure change</span>
        <span className={styles.magnitudeValue}>{comparison.disclosureChangeLabel ?? "Not available"}</span>
      </div>
      <QualityBadge
        dimension="disclosure-change"
        quality={comparison.disclosureChangeQuality}
        label={comparison.disclosureChangeQualityLabel}
        compact
      />

      {comparison.uncertaintyChangeLabel && (
        <p className={styles.signal}>
          <span className={styles.signalLabel}>Uncertainty:</span> {comparison.uncertaintyChangeLabel}
        </p>
      )}
      {comparison.riskIntroductionLabel && (
        <p className={styles.signal}>
          <span className={styles.signalLabel}>Risk introduced:</span> {comparison.riskIntroductionLabel}
        </p>
      )}

      <QualityBadge
        dimension="report-side"
        quality={comparison.reportSideQuality}
        label={comparison.reportSideQualityLabel}
        compact
      />
    </Link>
  );
}
