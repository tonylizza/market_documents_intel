import type { PassageComposition, PassageCompositionStatus } from "@/lib/domain/comparison";
import { formatCount } from "@/lib/formatting/numbers";
import { formatPassageStatusLabel } from "@/lib/formatting/labels";
import { EmptyState } from "./EmptyState";
import styles from "./PassageCompositionSection.module.css";

export interface PassageCompositionSectionProps {
  composition: PassageComposition;
}

/** Fixed category order -> fixed categorical color slot -- color follows
 * the category identity, never a value-based rank, so a bucket's color
 * never shifts between comparisons. Colors are the dataviz skill's
 * validated categorical palette (`--viz-cat-*`); the app's own brand
 * `--chart-*` tokens failed CVD/contrast validation for 6-way identity
 * encoding (see styles/tokens.css). */
const STATUS_COLOR_VAR: Record<PassageCompositionStatus, string> = {
  NEW: "var(--viz-cat-1)",
  REMOVED: "var(--viz-cat-2)",
  SUBSTANTIALLY_MODIFIED: "var(--viz-cat-3)",
  LIGHTLY_MODIFIED: "var(--viz-cat-4)",
  UNCHANGED: "var(--viz-cat-5)",
  AMBIGUOUS: "var(--viz-cat-6)",
};

function formatShare(share: number): string {
  return `${(share * 100).toFixed(1)}%`;
}

/**
 * Passage-alignment composition: count cards + one compact 100%-stacked bar
 * (six fixed-order segments, 2px surface gaps between them per the dataviz
 * mark spec) + a quality note. The bar and cards read the same
 * `composition.buckets` -- never two different totals.
 */
export function PassageCompositionSection({ composition }: PassageCompositionSectionProps) {
  if (composition.totalCount === 0) {
    return (
      <EmptyState
        title="No passage-composition data available"
        description="No aligned passages were published for this comparison."
      />
    );
  }

  return (
    <div className={styles.wrapper}>
      <div className={styles.cards}>
        {composition.buckets.map((bucket) => (
          <div className={styles.card} key={bucket.status}>
            <span className={styles.swatch} style={{ background: STATUS_COLOR_VAR[bucket.status] }} aria-hidden="true" />
            <span className={styles.cardLabel}>{formatPassageStatusLabel(bucket.status)}</span>
            <span className={styles.cardCount}>{formatCount(bucket.count)}</span>
            <span className={styles.cardShare}>{formatShare(bucket.share)}</span>
          </div>
        ))}
      </div>

      <div
        className={styles.stackedBar}
        role="img"
        aria-label={composition.buckets
          .map((bucket) => `${formatPassageStatusLabel(bucket.status)}: ${formatShare(bucket.share)} (${formatCount(bucket.count)} passages)`)
          .join(", ")}
      >
        {composition.buckets
          .filter((bucket) => bucket.count > 0)
          .map((bucket) => (
            <span
              key={bucket.status}
              className={styles.segment}
              style={{ width: `${bucket.share * 100}%`, background: STATUS_COLOR_VAR[bucket.status] }}
            />
          ))}
      </div>

      <p className={styles.total}>{formatCount(composition.totalCount)} aligned passages total</p>
      <p className={styles.qualityNote}>{composition.qualityNote}</p>
    </div>
  );
}

