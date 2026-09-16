import type { StructuredTableComparison } from "@/lib/domain/cutover-comparison";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import styles from "./StructuredTableComparisonSection.module.css";

export interface StructuredTableComparisonSectionProps {
  structured: StructuredTableComparison;
}

const UNRESOLVED_COPY: Record<string, { title: string; description: string }> = {
  UNRESOLVED_UPSTREAM: {
    title: "Comparison unavailable for this report pair",
    description: "This table could not be resolved reliably between these two reports.",
  },
  AMBIGUOUS: {
    title: "Comparison unavailable for this report pair",
    description: "This table matched more than one candidate across the two reports and could not be resolved automatically.",
  },
  REVIEW_REQUIRED: {
    title: "Review required",
    description: "This table comparison did not meet the bar for an automated result and needs manual review.",
  },
  NOT_AVAILABLE: {
    title: "Comparison unavailable for this report pair",
    description: "No automated result is available for this table.",
  },
};

function formatCellValue(raw: string | null, numeric: number | null): string {
  if (raw !== null) return raw;
  if (numeric !== null) return String(numeric);
  return "—";
}

/**
 * Track 7A.3/7A.4: renders one Track 7C.6 structured-table comparison as an
 * actual table -- row/column alignment and value-change events, never
 * flattened into prose. Unresolved: neutral copy, never the raw enum text.
 */
export function StructuredTableComparisonSection({ structured }: StructuredTableComparisonSectionProps) {
  const familyLabel = formatCategoryLabel(structured.tableFamilyKey);

  if (structured.status !== "RESOLVED") {
    const copy = UNRESOLVED_COPY[structured.status] ?? UNRESOLVED_COPY.NOT_AVAILABLE;
    return (
      <div className={styles.unresolved} data-status={structured.status} data-table-family={structured.tableFamilyKey} role="status">
        <p className={styles.unresolvedTitle}>{copy.title}</p>
        <p className={styles.unresolvedDescription}>
          {familyLabel}: {copy.description}
        </p>
      </div>
    );
  }

  return (
    <div data-status={structured.status} data-table-family={structured.tableFamilyKey}>
      <p className={styles.familyLabel}>{familyLabel}</p>

      {structured.rowAlignments.length > 0 && (
        <table className={styles.table}>
          <caption className="visually-hidden">{familyLabel}: row alignment</caption>
          <thead>
            <tr>
              <th scope="col">Earlier row</th>
              <th scope="col">Later row</th>
              <th scope="col">Status</th>
              <th scope="col">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {structured.rowAlignments.map((ra, index) => (
              <tr key={index}>
                <td>{ra.earlierRowIdentity ?? "—"}</td>
                <td>{ra.laterRowIdentity ?? "—"}</td>
                <td>{formatCategoryLabel(ra.status)}</td>
                <td>{formatCategoryLabel(ra.confidence)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {structured.valueChangeEvents.length > 0 && (
        <table className={styles.table}>
          <caption className="visually-hidden">{familyLabel}: value changes</caption>
          <thead>
            <tr>
              <th scope="col">Row</th>
              <th scope="col">Column</th>
              <th scope="col">Event</th>
              <th scope="col">Earlier value</th>
              <th scope="col">Later value</th>
              <th scope="col">Change</th>
            </tr>
          </thead>
          <tbody>
            {structured.valueChangeEvents.map((ev, index) => (
              <tr key={index}>
                <td>{ev.rowIdentity ?? "—"}</td>
                <td>{ev.columnNormalizedKey ? formatCategoryLabel(ev.columnNormalizedKey) : "—"}</td>
                <td>{formatCategoryLabel(ev.eventType)}</td>
                <td>{formatCellValue(ev.earlierRawValue, ev.earlierNumeric)}</td>
                <td>{formatCellValue(ev.laterRawValue, ev.laterNumeric)}</td>
                <td>{ev.pctChange !== null ? `${ev.pctChange >= 0 ? "+" : ""}${(ev.pctChange * 100).toFixed(1)}%` : ev.absoluteChange !== null ? String(ev.absoluteChange) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {structured.footnotes.length > 0 && (
        <ul className={styles.footnotes}>
          {structured.footnotes.map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
