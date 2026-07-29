import Link from "next/link";
import type { ComparisonEvidenceItem, PassageSideExcerpt } from "@/lib/domain/passage";
import { HighlightedText } from "@/components/HighlightedText";
import { TechnicalDetails } from "@/components/TechnicalDetails";
import { DefinitionList } from "@/components/DefinitionList";
import { formatAlignmentStatusLabel, formatAlignmentTypeLabel } from "@/lib/config/passage-vocabulary";
import { formatMetricValue } from "@/lib/formatting/numbers";
import styles from "./ComparisonEvidenceRow.module.css";

export interface ComparisonEvidenceRowProps {
  item: ComparisonEvidenceItem;
}

function SideExcerpt({ label, side }: { label: string; side: PassageSideExcerpt | null }) {
  return (
    <div className={styles.side}>
      <p className={styles.sideLabel}>{label}</p>
      {side ? (
        <>
          <p className={styles.sideHeading}>{side.heading ?? "(No heading)"}</p>
          <p className={styles.sideExcerpt}>
            <HighlightedText spans={side.excerpt} />
          </p>
          <p className={styles.sideMeta}>
            {side.firstPageNumber === side.lastPageNumber ? `Page ${side.firstPageNumber}` : `Pages ${side.firstPageNumber}–${side.lastPageNumber}`}
          </p>
        </>
      ) : (
        <p className={styles.sideMissing}>No aligned {label.toLowerCase()} passage.</p>
      )}
    </div>
  );
}

export function ComparisonEvidenceRow({ item }: ComparisonEvidenceRowProps) {
  return (
    <article className={styles.row}>
      <div className={styles.badges}>
        <span className={styles.badge}>{formatAlignmentStatusLabel(item.alignmentStatus)}</span>
        <span className={styles.badge}>{item.confidenceLabel}</span>
        <span className={styles.badge}>{formatAlignmentTypeLabel(item.alignmentType)}</span>
        {item.collisionFlag && <span className={styles.badge}>Collision flagged</span>}
        {item.splitMergeFlag && <span className={styles.badge}>Split/merge flagged</span>}
      </div>

      <div className={styles.sides}>
        <SideExcerpt label="Earlier" side={item.earlier} />
        <SideExcerpt label="Later" side={item.later} />
      </div>

      <TechnicalDetails summary="Technical details">
        <DefinitionList
          items={[{ term: "Content score", description: formatMetricValue(item.contentScore, "score_0_1") ?? "Not available" }]}
        />
      </TechnicalDetails>

      <p className={styles.footer}>
        <Link href={`/passages/${item.passageComparisonId}`}>View full passage evidence →</Link>
      </p>
    </article>
  );
}
