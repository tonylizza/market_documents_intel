import Link from "next/link";
import type { ComparisonPreview } from "@/lib/domain/comparison";
import { formatComparisonPeriod } from "@/lib/formatting/dates";
import { QualityBadge } from "./QualityBadge";
import { HeadlineMetricCard } from "./HeadlineMetricCard";
import { DeterministicFindingsList } from "./DeterministicFindingsList";
import styles from "./ComparisonPreviewSection.module.css";

export interface ComparisonPreviewSectionProps {
  preview: ComparisonPreview;
}

/** Compact preview shown on the company page for the currently selected
 * comparison -- up to three findings, six headline metric cards, and both
 * report-side/alignment-change quality, with a link through to the full
 * `/comparisons/[comparisonId]` page for the rest (language tables, passage
 * composition, technical details). */
export function ComparisonPreviewSection({ preview }: ComparisonPreviewSectionProps) {
  const { comparison, findings, headlineMetrics } = preview;
  const period = formatComparisonPeriod(comparison.earlierPeriodEnd, comparison.laterPeriodEnd);

  return (
    <div className={styles.wrapper}>
      <div className={styles.header}>
        <h3 className={styles.period}>{period ?? "Selected comparison"}</h3>
        <div className={styles.badges}>
          <QualityBadge dimension="report-side" quality={comparison.reportSideQuality} label={comparison.reportSideQualityLabel} compact />
          <QualityBadge
            dimension="alignment-change"
            quality={comparison.alignmentChangeQuality}
            label={comparison.alignmentChangeQualityLabel}
            compact
          />
        </div>
      </div>

      <DeterministicFindingsList findings={findings} />

      <div className={styles.metricGrid}>
        {headlineMetrics.map((metric) => (
          <HeadlineMetricCard metric={metric} key={metric.metricKey} />
        ))}
      </div>

      <Link href={`/comparisons/${comparison.id}`} className={styles.fullLink}>
        View full comparison →
      </Link>
    </div>
  );
}
