import Link from "next/link";
import type { DiscoveryItem } from "@/lib/domain/discovery";
import { formatComparisonPeriod } from "@/lib/formatting/dates";
import { EmptyState } from "./EmptyState";
import styles from "./DiscoveryResultsTable.module.css";

export interface DiscoveryResultsTableProps {
  items: readonly DiscoveryItem[];
}

/**
 * Ranked results table -- row order is exactly `items`'s incoming order
 * (the repository's `ORDER BY rank`, itself the database's deterministic
 * tie-break order). Never re-sorted client-side from rounded display
 * values.
 */
export function DiscoveryResultsTable({ items }: DiscoveryResultsTableProps) {
  if (items.length === 0) {
    return (
      <EmptyState
        title="No results for these filters"
        description="Try a different company, period range, or a lower minimum quality."
      />
    );
  }

  return (
    <table className={styles.table}>
      <caption className="visually-hidden">Discovery ranking results</caption>
      <thead>
        <tr>
          <th scope="col">Rank</th>
          <th scope="col">Company</th>
          <th scope="col">Comparison periods</th>
          <th scope="col">Finding</th>
          <th scope="col">Value</th>
          <th scope="col">Quality</th>
          <th scope="col">
            <span className="visually-hidden">Details</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id}>
            <td>{item.rank}</td>
            <td>
              {item.companyName} ({item.companyTicker})
            </td>
            <td>{formatComparisonPeriod(item.earlierPeriodEnd, item.laterPeriodEnd) ?? "—"}</td>
            <td>{item.findingHeadline}</td>
            <td>{item.supportingValueDisplay ?? item.supportingValue}</td>
            <td>{item.qualityLabel}</td>
            <td>
              <Link href={`/comparisons/${item.reportComparisonId}`}>View comparison →</Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
