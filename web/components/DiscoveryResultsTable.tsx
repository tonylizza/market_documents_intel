import Link from "next/link";
import type { DiscoveryItem, FinancialConditionCompanyStatus } from "@/lib/domain/discovery";
import { formatComparisonPeriod } from "@/lib/formatting/dates";
import { formatMetricValue } from "@/lib/formatting/numbers";
import { EmptyState } from "./EmptyState";
import styles from "./DiscoveryResultsTable.module.css";

export interface DiscoveryResultsTableProps {
  items: readonly DiscoveryItem[];
  /** Track 7F.4 item 8 -- when set (financial-condition shift, company
   * filter active, zero eligible items), replaces the generic empty state
   * with one of three distinct, explicit states instead of collapsing them
   * all into "No results for these filters." */
  financialConditionCompanyStatus?: FinancialConditionCompanyStatus | null;
}

/**
 * Ranked results table -- row order is exactly `items`'s incoming order
 * (the repository's `ORDER BY rank`, itself the database's deterministic
 * tie-break order). Never re-sorted client-side from rounded display
 * values.
 */
export function DiscoveryResultsTable({ items, financialConditionCompanyStatus }: DiscoveryResultsTableProps) {
  if (items.length === 0) {
    if (financialConditionCompanyStatus?.status === "no_comparisons") {
      return (
        <EmptyState
          title="No comparisons available for this company"
          description="This company has no published report comparisons yet."
        />
      );
    }
    if (financialConditionCompanyStatus?.status === "failed_quality") {
      return (
        <EmptyState
          title="This company's financial-condition results didn't clear the quality gate"
          description="Report-side signal quality wasn't GOOD or USABLE (or wasn't primary-eligible) for any comparison, so no financial-condition value can be shown."
        />
      );
    }
    if (financialConditionCompanyStatus?.status === "below_materiality") {
      const { observedValue, threshold, reportComparisonId, earlierPeriodEnd, laterPeriodEnd } = financialConditionCompanyStatus;
      return (
        <EmptyState
          title="Below materiality threshold"
          description={`This company's largest quality-eligible financial-condition language share change (${formatComparisonPeriod(earlierPeriodEnd, laterPeriodEnd) ?? "unknown period"}) was ${formatMetricValue(observedValue, "share")}, which does not clear the ${formatMetricValue(threshold, "share")} materiality threshold. Not ranked as an eligible Discover finding.`}
        >
          <Link href={`/comparisons/${reportComparisonId}`}>View this comparison →</Link>
        </EmptyState>
      );
    }
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
