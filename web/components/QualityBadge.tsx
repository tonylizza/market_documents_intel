import { qualityVisualVariant, QUALITY_DIMENSION_DISPLAY_NAMES, type QualityDimension, type RawQuality } from "@/lib/domain/quality";
import { resolveQualityLabel } from "@/lib/formatting/labels";
import styles from "./QualityBadge.module.css";

export interface QualityBadgeProps {
  dimension: QualityDimension;
  quality: RawQuality | null;
  label: string | null;
  /** Compact form omits the dimension name prefix from the visible text
   * (still present in the accessible name) -- used inline on cards where
   * context already makes the dimension clear. */
  compact?: boolean;
}

/**
 * Renders one quality dimension's status as text + color, never color
 * alone. `dimension` is required and used both for the accessible name and
 * to select the correct label vocabulary when `label` is missing --
 * report-side, alignment-change, and disclosure-change are never collapsed
 * into one generic mapping.
 */
export function QualityBadge({ dimension, quality, label, compact = false }: QualityBadgeProps) {
  const resolvedLabel = resolveQualityLabel(dimension, quality, label);
  const variant = qualityVisualVariant(quality);
  const dimensionName = QUALITY_DIMENSION_DISPLAY_NAMES[dimension];
  const visibleText = resolvedLabel ?? "Not available";

  return (
    <span
      className={`${styles.badge} ${styles[variant]}`}
      role="status"
      aria-label={`${dimensionName}: ${visibleText}`}
    >
      {!compact && <span className={styles.dimension}>{dimensionName}</span>}
      <span className={styles.label}>{visibleText}</span>
    </span>
  );
}
