import { QUALITY_DIMENSION_DISPLAY_NAMES, type QualityDimension, type RawQuality } from "@/lib/domain/quality";
import { resolveQualityLabel } from "@/lib/formatting/labels";
import { QualityBadge } from "./QualityBadge";
import styles from "./StatusLegend.module.css";

const TIERS: readonly RawQuality[] = ["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"];

export interface StatusLegendProps {
  dimension: QualityDimension;
}

/** Static reference legend showing all four tiers of one quality
 * dimension's vocabulary -- used on the Methodology page so a reader can
 * see the full vocabulary at a glance, not just whichever tier happens to
 * appear on a given comparison. */
export function StatusLegend({ dimension }: StatusLegendProps) {
  return (
    <div className={styles.wrapper}>
      <h4 className={styles.heading}>{QUALITY_DIMENSION_DISPLAY_NAMES[dimension]}</h4>
      <ul className={styles.list}>
        {TIERS.map((tier) => (
          <li key={tier}>
            <QualityBadge dimension={dimension} quality={tier} label={resolveQualityLabel(dimension, tier, null)} compact />
          </li>
        ))}
      </ul>
    </div>
  );
}
