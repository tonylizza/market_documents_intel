import type { HeadlineMetric } from "@/lib/domain/comparison";
import { QualityBadge } from "./QualityBadge";
import { TechnicalDetails } from "./TechnicalDetails";
import { DefinitionList } from "./DefinitionList";
import styles from "./HeadlineMetricCard.module.css";

export interface HeadlineMetricCardProps {
  metric: HeadlineMetric;
}

/** One of the six fixed headline metric cards -- plain-language label,
 * value, unit, quality treatment, a short explanation, and a
 * collapsed-by-default technical expander. Never a single merged
 * "overall quality" badge: `metric.qualityDimension` picks the correct one
 * of the three independent vocabularies. */
export function HeadlineMetricCard({ metric }: HeadlineMetricCardProps) {
  return (
    <div className={styles.card}>
      <h4 className={styles.title}>{metric.displayName}</h4>
      <p className={styles.value}>{metric.value === null ? "Not available" : (metric.valueDisplay ?? String(metric.value))}</p>
      <p className={styles.explanation}>{metric.explanation}</p>

      <QualityBadge dimension={metric.qualityDimension} quality={metric.quality} label={metric.qualityLabel} compact />

      {metric.reviewQualifiedExploratory && (
        <p className={styles.exploratoryNote}>
          This score is exploratory in the current corpus and is excluded from primary discovery rankings.
        </p>
      )}

      <TechnicalDetails summary="Technical details">
        <DefinitionList
          items={[
            { term: "Metric key", description: metric.metricKey },
            { term: "Raw value", description: metric.value === null ? "Not available" : String(metric.value) },
            { term: "Unit", description: metric.unit },
            { term: "Quality", description: metric.qualityLabel ?? "Not available" },
            { term: "Primary eligible", description: metric.primaryEligible === null ? "Not available" : metric.primaryEligible ? "Yes" : "No" },
          ]}
        />
      </TechnicalDetails>
    </div>
  );
}
