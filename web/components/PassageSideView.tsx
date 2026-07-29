import type { PassageSideDetail } from "@/lib/domain/passage";
import { formatPassageTypeLabel, formatStructuredContentCategoryLabel } from "@/lib/config/passage-vocabulary";
import { formatCount } from "@/lib/formatting/numbers";
import styles from "./PassageSideView.module.css";

export interface PassageSideViewProps {
  label: string;
  side: PassageSideDetail;
}

/** Full, uncapped text for one side of a passage comparison -- used for the
 * primary side of NEW/REMOVED and for a one-sided AMBIGUOUS passage. Full
 * text is never truncated here (only the `/passages` search excerpt is
 * bounded). */
export function PassageSideView({ label, side }: PassageSideViewProps) {
  const structuredLabel = side.structuredContentCategory ? formatStructuredContentCategoryLabel(side.structuredContentCategory) : null;

  return (
    <div className={styles.wrapper}>
      <h3 className={styles.label}>{label}</h3>
      <p className={styles.heading}>{side.heading ?? "(No heading)"}</p>
      <p className={styles.text}>{side.text}</p>
      <div className={styles.meta}>
        <span>{side.firstPageNumber === side.lastPageNumber ? `Page ${side.firstPageNumber}` : `Pages ${side.firstPageNumber}–${side.lastPageNumber}`}</span>
        <span>{formatCount(side.wordCount)} words</span>
        <span>{formatPassageTypeLabel(side.passageType)}</span>
        {structuredLabel && <span>{structuredLabel}</span>}
        {side.primaryNarrativeEligible && <span>Primary narrative eligible</span>}
        {side.featureEligible && <span>Feature eligible</span>}
      </div>
    </div>
  );
}
