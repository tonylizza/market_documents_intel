import type { DeterministicFinding } from "@/lib/domain/comparison";
import { EmptyState } from "./EmptyState";
import styles from "./DeterministicFindingsList.module.css";

export interface DeterministicFindingsListProps {
  findings: readonly DeterministicFinding[];
}

const SLOT_LABEL: Record<DeterministicFinding["slot"], string> = {
  primary: "Primary finding",
  secondary: "Secondary finding",
  tertiary: "Tertiary finding",
};

/** Renders up to three published findings via the controlled finding-copy
 * mapping -- never regenerates or re-ranks findings from chart values, and
 * a comparison with fewer than three eligible candidates simply renders
 * fewer items (never a placeholder "no finding" card in an unfilled slot). */
export function DeterministicFindingsList({ findings }: DeterministicFindingsListProps) {
  if (findings.length === 0) {
    return (
      <EmptyState
        title="No deterministic findings for this comparison"
        description="No candidate change cleared its eligibility gate for this comparison."
      />
    );
  }

  return (
    <ol className={styles.list}>
      {findings.map((finding) => (
        <li key={finding.slot} className={styles.item}>
          <span className={styles.slot}>{SLOT_LABEL[finding.slot]}</span>
          <h4 className={styles.headline}>{finding.headline}</h4>
          <p className={styles.description}>{finding.description}</p>
          {finding.supportingValueDisplay && <p className={styles.supportingValue}>{finding.supportingValueDisplay}</p>}
        </li>
      ))}
    </ol>
  );
}
