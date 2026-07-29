"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { LanguageMetric } from "@/lib/domain/comparison";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import { EmptyState } from "./EmptyState";
import styles from "./LanguageMetricsSection.module.css";

export type LanguageMetricsVariant = "report-side" | "alignment-change";

export interface LanguageMetricsSectionProps {
  metrics: readonly LanguageMetric[];
  variant: LanguageMetricsVariant;
}

type SortKey = "category" | "earlier" | "later" | "change";
type SortDirection = "asc" | "desc";

interface Row {
  id: string;
  category: string;
  displayCategory: string;
  earlierRatePer1000: number | null;
  laterRatePer1000: number | null;
  rateChange: number | null;
  introducedRatePer1000: number | null;
  removedRatePer1000: number | null;
  retainedCount: number | null;
  chartValue: number;
}

function toRows(metrics: readonly LanguageMetric[], variant: LanguageMetricsVariant): Row[] {
  return metrics.map((metric) => {
    const chartValue =
      variant === "report-side"
        ? (metric.rateChange ?? 0)
        : (metric.introducedRatePer1000 ?? 0) - (metric.removedRatePer1000 ?? 0);
    return {
      id: metric.id,
      category: metric.category,
      displayCategory: formatCategoryLabel(metric.category),
      earlierRatePer1000: metric.earlierRatePer1000,
      laterRatePer1000: metric.laterRatePer1000,
      rateChange: metric.rateChange,
      introducedRatePer1000: metric.introducedRatePer1000,
      removedRatePer1000: metric.removedRatePer1000,
      retainedCount: metric.retainedCount,
      chartValue,
    };
  });
}

function sortRows(rows: Row[], key: SortKey, direction: SortDirection): Row[] {
  const factor = direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (key === "category") return factor * a.displayCategory.localeCompare(b.displayCategory);
    const field = key === "earlier" ? "earlierRatePer1000" : key === "later" ? "laterRatePer1000" : "rateChange";
    const av = a[field] ?? Number.NEGATIVE_INFINITY;
    const bv = b[field] ?? Number.NEGATIVE_INFINITY;
    return factor * (av - bv);
  });
}

/**
 * Report-side / alignment-change language metrics -- one horizontal
 * diverging bar chart (single hue; bar direction, not color, carries the
 * increase/decrease sign, per the milestone's "never a value-judgment
 * color" rule) plus a sortable table reading the exact same rows. Handles
 * an empty metric list without a misleading zero-filled chart.
 */
export function LanguageMetricsSection({ metrics, variant }: LanguageMetricsSectionProps) {
  const [sortKey, setSortKey] = useState<SortKey>("change");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const rows = useMemo(() => toRows(metrics, variant), [metrics, variant]);
  const sortedRows = useMemo(() => sortRows(rows, sortKey, sortDirection), [rows, sortKey, sortDirection]);
  const chartRows = useMemo(() => [...rows].sort((a, b) => b.chartValue - a.chartValue), [rows]);

  if (rows.length === 0) {
    return <EmptyState title="No language metrics available" description="This scope has no published language metrics for this comparison." />;
  }

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDirection((direction) => (direction === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("desc");
    }
  }

  return (
    <div className={styles.wrapper}>
      <p className="visually-hidden">
        {`${variant === "report-side" ? "Report-side" : "Alignment-change"} language metrics across ${rows.length} categories. See the table below for exact earlier/later rates and change values.`}
      </p>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={Math.max(180, chartRows.length * 34)}>
          <BarChart data={chartRows} layout="vertical" margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
            <CartesianGrid stroke="var(--viz-grid)" strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" stroke="var(--viz-axis)" tick={{ fill: "var(--viz-ink-muted)", fontSize: 12 }} />
            <YAxis
              type="category"
              dataKey="displayCategory"
              width={140}
              stroke="var(--viz-axis)"
              tick={{ fill: "var(--viz-ink-muted)", fontSize: 12 }}
            />
            <ReferenceLine x={0} stroke="var(--viz-axis)" />
            <Tooltip
              formatter={(value) => {
                const numeric = typeof value === "number" ? value : Number(value);
                return [`${numeric >= 0 ? "+" : ""}${numeric.toFixed(2)} / 1,000 words`, "Change"];
              }}
              contentStyle={{ background: "var(--color-surface)", border: "1px solid var(--color-border-strong)", fontSize: 12 }}
            />
            <Bar dataKey="chartValue" fill="var(--viz-cat-1)" isAnimationActive={false} radius={2} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">
              <button type="button" onClick={() => toggleSort("category")} className={styles.sortButton}>
                Category {sortKey === "category" && (sortDirection === "asc" ? "▲" : "▼")}
              </button>
            </th>
            {variant === "report-side" ? (
              <>
                <th scope="col">
                  <button type="button" onClick={() => toggleSort("earlier")} className={styles.sortButton}>
                    Earlier rate {sortKey === "earlier" && (sortDirection === "asc" ? "▲" : "▼")}
                  </button>
                </th>
                <th scope="col">
                  <button type="button" onClick={() => toggleSort("later")} className={styles.sortButton}>
                    Later rate {sortKey === "later" && (sortDirection === "asc" ? "▲" : "▼")}
                  </button>
                </th>
                <th scope="col">
                  <button type="button" onClick={() => toggleSort("change")} className={styles.sortButton}>
                    Change {sortKey === "change" && (sortDirection === "asc" ? "▲" : "▼")}
                  </button>
                </th>
              </>
            ) : (
              <>
                <th scope="col">Introduced</th>
                <th scope="col">Removed</th>
                <th scope="col">Retained</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr key={row.id}>
              <td>{row.displayCategory}</td>
              {variant === "report-side" ? (
                <>
                  <td>{row.earlierRatePer1000 !== null ? `${row.earlierRatePer1000.toFixed(2)} / 1,000 words` : "—"}</td>
                  <td>{row.laterRatePer1000 !== null ? `${row.laterRatePer1000.toFixed(2)} / 1,000 words` : "—"}</td>
                  <td>{row.rateChange !== null ? `${row.rateChange >= 0 ? "+" : ""}${row.rateChange.toFixed(2)} / 1,000 words` : "—"}</td>
                </>
              ) : (
                <>
                  <td>{row.introducedRatePer1000 !== null ? `${row.introducedRatePer1000.toFixed(2)} / 1,000 words` : "—"}</td>
                  <td>{row.removedRatePer1000 !== null ? `${row.removedRatePer1000.toFixed(2)} / 1,000 words` : "—"}</td>
                  <td>{row.retainedCount ?? "—"}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
