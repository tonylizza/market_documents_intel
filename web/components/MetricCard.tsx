import styles from "./MetricCard.module.css";

export interface MetricCardProps {
  title: string;
  subtitle?: string;
  value: string;
  qualityLabel?: string;
}

/** Small, single-metric card used in the latest-signals sections and the
 * Methodology page's metric catalog. */
export function MetricCard({ title, subtitle, value, qualityLabel }: MetricCardProps) {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={styles.title}>{title}</span>
        {subtitle && <span className={styles.subtitle}>{subtitle}</span>}
      </div>
      <span className={styles.value}>{value}</span>
      {qualityLabel && <span className={styles.quality}>{qualityLabel}</span>}
    </div>
  );
}
