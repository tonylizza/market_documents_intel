"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from "recharts";
import type { CompanyMetricPoint } from "@/lib/domain/company";
import type { ComparisonMetricConfig } from "@/lib/config/comparison";
import { formatPeriodEnd } from "@/lib/formatting/dates";
import { formatMetricValue } from "@/lib/formatting/numbers";
import { EmptyState } from "./EmptyState";
import { TechnicalDetails } from "./TechnicalDetails";
import styles from "./FullHistoryChart.module.css";

export interface FullHistoryChartProps {
  points: readonly CompanyMetricPoint[];
  metric: ComparisonMetricConfig;
}

interface ChartDatum {
  timestamp: number;
  value: number | null;
  comparisonId: string;
  label: string | null;
  periodDisplay: string;
  isIrregularGap: boolean;
  isTransition: boolean;
  isHistoricalPeakChange: boolean;
}

function toChartData(points: readonly CompanyMetricPoint[]): ChartDatum[] {
  return points
    .filter((point) => point.laterPeriodEnd !== null)
    .map((point) => ({
      timestamp: Date.parse(point.laterPeriodEnd as string),
      value: point.value,
      comparisonId: point.comparisonId,
      label: point.label,
      periodDisplay: formatPeriodEnd(point.laterPeriodEnd) ?? "Unknown date",
      isIrregularGap: point.isIrregularGap,
      isTransition: point.isTransition,
      isHistoricalPeakChange: point.isHistoricalPeakChange,
    }));
}

/** Custom marker: a filled circle by default, a ring for an irregular-gap
 * comparison, and a gold-outlined circle for the historical-peak change --
 * shape/border, never color alone, so the distinction survives for
 * colorblind and grayscale-print readers. */
function HistoryDot(props: { cx?: number; cy?: number; payload?: ChartDatum }) {
  const { cx, cy, payload } = props;
  if (cx === undefined || cy === undefined || !payload || payload.value === null) return null;
  const isPeak = payload.isHistoricalPeakChange;
  const isIrregular = payload.isIrregularGap;
  return (
    <g>
      <circle cx={cx} cy={cy} r={isPeak ? 6 : 4} fill="var(--viz-cat-1)" stroke={isPeak ? "var(--color-gold-500)" : "var(--color-surface)"} strokeWidth={isPeak ? 3 : 1.5} />
      {isIrregular && <circle cx={cx} cy={cy} r={9} fill="none" stroke="var(--color-warning)" strokeWidth={1.5} strokeDasharray="2 2" />}
    </g>
  );
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: ChartDatum }[] }) {
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0].payload;
  return (
    <div className={styles.tooltip} role="status">
      <p className={styles.tooltipDate}>{datum.periodDisplay}</p>
      <p className={styles.tooltipValue}>{datum.value === null ? "Not available" : datum.label ?? String(datum.value)}</p>
      {datum.isTransition && <p className={styles.tooltipFlag}>Transition report</p>}
      {datum.isIrregularGap && <p className={styles.tooltipFlag}>Irregular reporting gap</p>}
      {datum.isHistoricalPeakChange && <p className={styles.tooltipFlag}>Historical peak change</p>}
    </div>
  );
}

/**
 * Full-history line chart for one selected metric. Uses actual comparison
 * dates on the x-axis (numeric/time scale, not an evenly spaced index), so
 * irregular gaps between reports are visible as uneven spacing rather than
 * hidden. Always paired with a table (`View data table`) of the exact same
 * points -- the chart is never the only way to read the data.
 */
export function FullHistoryChart({ points, metric }: FullHistoryChartProps) {
  const data = toChartData(points);

  if (data.length === 0) {
    return <EmptyState title="No comparison history available" description="This company has no comparisons to chart yet." />;
  }

  const hasAnyValue = data.some((d) => d.value !== null);

  return (
    <div className={styles.wrapper}>
      <p className="visually-hidden">
        {`Line chart of ${metric.displayName} across ${data.length} comparison${data.length === 1 ? "" : "s"}, from ${data[0].periodDisplay} to ${data[data.length - 1].periodDisplay}. Use the data table below for exact values.`}
      </p>

      {!hasAnyValue ? (
        <EmptyState
          title={`${metric.displayName} is not available`}
          description="No comparison in this range has a published value for this metric."
        />
      ) : (
        <div className={styles.chartArea} aria-hidden="true">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={data} margin={{ top: 16, right: 16, bottom: 8, left: 8 }}>
              <CartesianGrid stroke="var(--viz-grid)" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="timestamp"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(value: number) => formatPeriodEnd(new Date(value).toISOString().slice(0, 10)) ?? ""}
                stroke="var(--viz-axis)"
                tick={{ fill: "var(--viz-ink-muted)", fontSize: 12 }}
              />
              <YAxis
                stroke="var(--viz-axis)"
                tick={{ fill: "var(--viz-ink-muted)", fontSize: 12 }}
                tickFormatter={(value: number) => formatMetricValue(value, metric.unit) ?? String(value)}
                width={64}
              />
              <Tooltip content={<ChartTooltip />} />
              <Line
                type="monotone"
                dataKey="value"
                stroke="var(--viz-cat-1)"
                strokeWidth={2}
                dot={<HistoryDot />}
                activeDot={{ r: 6 }}
                connectNulls={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <ul className={styles.legend}>
        <li>
          <span className={styles.legendDotPeak} aria-hidden="true" /> Historical peak change
        </li>
        <li>
          <span className={styles.legendDotIrregular} aria-hidden="true" /> Irregular reporting gap
        </li>
      </ul>

      <TechnicalDetails summary="View data table">
        <table className={styles.table}>
          <caption className="visually-hidden">{metric.displayName} by comparison period</caption>
          <thead>
            <tr>
              <th scope="col">Period</th>
              <th scope="col">{metric.displayName}</th>
              <th scope="col">Flags</th>
            </tr>
          </thead>
          <tbody>
            {data.map((datum) => (
              <tr key={datum.comparisonId}>
                <td>{datum.periodDisplay}</td>
                <td>{datum.value === null ? "Not available" : (datum.label ?? formatMetricValue(datum.value, metric.unit))}</td>
                <td>
                  {[
                    datum.isTransition && "Transition",
                    datum.isIrregularGap && "Irregular gap",
                    datum.isHistoricalPeakChange && "Historical peak",
                  ]
                    .filter(Boolean)
                    .join(", ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TechnicalDetails>
    </div>
  );
}
