import type { LanguageMetric } from "@/lib/domain/comparison";
import { formatMetricValue } from "@/lib/formatting/numbers";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import { DefinitionList } from "./DefinitionList";
import { EmptyState } from "./EmptyState";
import styles from "./FinancialConditionSupportingDetail.module.css";

export interface FinancialConditionSupportingDetailProps {
  /** M3 -- financial-condition share of classified topic language; the
   * Discover ranking metric before Track 7F.9, supporting detail since. */
  shareChange?: number | null;
  topicMixChange: number | null;
  subcategoryMovers: readonly LanguageMetric[];
}

/**
 * Track 7F.4 items 11/12 -- M6b (topic-mix change, unsigned, never given a
 * +/- direction) plus the top financial_condition subcategory movers by
 * absolute hit-count change. Purely supporting detail for a financial-
 * condition finding -- never the Discover ranking metric (since Track 7F.9
 * that's the financial-condition topic change; M3 is shown here as
 * supporting detail).
 */
export function FinancialConditionSupportingDetail({
  shareChange = null,
  topicMixChange,
  subcategoryMovers,
}: FinancialConditionSupportingDetailProps) {
  const movers = [...subcategoryMovers].sort((a, b) => {
    const aChange = Math.abs((a.laterCount ?? 0) - (a.earlierCount ?? 0));
    const bChange = Math.abs((b.laterCount ?? 0) - (b.earlierCount ?? 0));
    return bChange - aChange;
  });

  return (
    <div className={styles.wrapper}>
      <DefinitionList
        items={[
          {
            term: "Share of classified topic language (M3)",
            description:
              (formatMetricValue(shareChange, "share") ?? "Not available") +
              " change -- financial-condition language as a share of all classified risk / financial-condition / governance / strategy language. Moves when other categories change too. Supporting detail only.",
          },
          {
            term: "Topic-mix change (M6b)",
            description:
              (formatMetricValue(topicMixChange, "distance_0_1") ?? "Not available") +
              " -- how much the mix of revenue/debt/cash-flow/etc. topics within financial-condition language changed. Supporting detail only; no positive/negative direction.",
          },
        ]}
      />

      {movers.length === 0 ? (
        <EmptyState
          title="No subcategory detail available"
          description="No financial-condition subcategory hits were recorded for this comparison."
        />
      ) : (
        <table className={styles.table}>
          <caption className="visually-hidden">Dominant financial-condition subcategory movers</caption>
          <thead>
            <tr>
              <th scope="col">Subcategory</th>
              <th scope="col">Earlier hits</th>
              <th scope="col">Later hits</th>
              <th scope="col">Change</th>
            </tr>
          </thead>
          <tbody>
            {movers.map((mover) => {
              const earlier = mover.earlierCount ?? 0;
              const later = mover.laterCount ?? 0;
              const change = later - earlier;
              return (
                <tr key={mover.id}>
                  <td>{mover.subcategory ? formatCategoryLabel(mover.subcategory) : "—"}</td>
                  <td>{earlier}</td>
                  <td>{later}</td>
                  <td>{`${change >= 0 ? "+" : ""}${change}`}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
