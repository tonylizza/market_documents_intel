"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { COMPARISON_METRICS, COMPARISON_METRIC_KEYS, type ComparisonMetricKey } from "@/lib/config/comparison";
import styles from "./MetricSelector.module.css";

export interface MetricSelectorProps {
  selected: ComparisonMetricKey;
}

/**
 * Bounded metric selector for the full-history chart -- exactly the seven
 * approved `COMPARISON_METRIC_KEYS`, never a generic/arbitrary metric
 * picker. Renders as real links (`?metric=...`, preserving `comparison=`),
 * so selection is URL-addressable and works without JavaScript.
 */
export function MetricSelector({ selected }: MetricSelectorProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  return (
    <div className={styles.wrapper} role="tablist" aria-label="Chart metric">
      {COMPARISON_METRIC_KEYS.map((key) => {
        const config = COMPARISON_METRICS[key];
        const params = new URLSearchParams(searchParams.toString());
        params.set("metric", key);
        const isSelected = key === selected;
        return (
          <Link
            key={key}
            href={`${pathname}?${params.toString()}`}
            role="tab"
            aria-selected={isSelected}
            className={`${styles.tab} ${isSelected ? styles.selected : ""}`}
          >
            {config.displayName}
            {config.reviewQualifiedInCurrentCorpus && <span className={styles.exploratoryFlag}>Exploratory</span>}
          </Link>
        );
      })}
    </div>
  );
}
