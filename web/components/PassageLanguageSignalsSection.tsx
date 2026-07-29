import type { PassageLanguageSignal, ReportSide } from "@/lib/domain/passage";
import { formatReportSideLabel } from "@/lib/config/passage-vocabulary";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import { EmptyState } from "@/components/EmptyState";
import styles from "./PassageLanguageSignalsSection.module.css";

export interface PassageLanguageSignalsSectionProps {
  signals: readonly PassageLanguageSignal[];
}

function flagLabel(signal: PassageLanguageSignal): string | null {
  if (signal.isIntroduced) return "Introduced";
  if (signal.isRemoved) return "Removed";
  if (signal.isRetained) return "Retained";
  return null;
}

/**
 * Passage-level financial-language signals, grouped by report side then by
 * category/subcategory -- fetched for this one passage comparison only
 * (`getPassageLanguageSignals`, never the 269,819-row bulk table). A
 * `subcategory === null` row is a real core-category signal
 * (uncertainty/positive/negative/etc.), not a missing value; upstream
 * nulls on count/rate fields are tolerated and rendered as "Not available".
 */
export function PassageLanguageSignalsSection({ signals }: PassageLanguageSignalsSectionProps) {
  const nonZero = signals.filter((signal) => signal.rawCount > 0);
  if (nonZero.length === 0) {
    return <EmptyState title="No language signals present" description="No published financial-language categories had a nonzero count for this passage." />;
  }

  const sides: ReportSide[] = ["EARLIER", "LATER"];

  return (
    <div className={styles.wrapper}>
      {sides.map((side) => {
        const sideSignals = nonZero.filter((signal) => signal.reportSide === side);
        if (sideSignals.length === 0) return null;
        return (
          <div key={side} className={styles.sideGroup}>
            <h4 className={styles.sideHeading}>{formatReportSideLabel(side)}</h4>
            <table className={styles.table}>
              <caption className="visually-hidden">
                {formatReportSideLabel(side)} language signals
              </caption>
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col">Raw count</th>
                  <th scope="col">Adjusted count</th>
                  <th scope="col">Negated count</th>
                  <th scope="col">Rate per 1,000</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {sideSignals.map((signal) => (
                  <tr key={`${signal.category}-${signal.subcategory ?? "core"}`}>
                    <td>
                      {formatCategoryLabel(signal.category)}
                      {signal.subcategory ? ` — ${formatCategoryLabel(signal.subcategory)}` : ""}
                    </td>
                    <td>{signal.rawCount}</td>
                    <td>{signal.adjustedCount ?? "Not available"}</td>
                    <td>{signal.negatedCount ?? "Not available"}</td>
                    <td>{signal.ratePer1000 !== null ? signal.ratePer1000.toFixed(2) : "Not available"}</td>
                    <td>{flagLabel(signal) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}
