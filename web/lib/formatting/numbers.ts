const INTEGER_FORMATTER = new Intl.NumberFormat("en-US");

export function formatCount(value: number): string {
  return INTEGER_FORMATTER.format(value);
}

export function formatPercentile(value: number | null): string | null {
  if (value === null || Number.isNaN(value)) return null;
  return `${Math.round(value)}th percentile`;
}

/**
 * Formats a metric's raw value according to its `unit` (from
 * `app.metric_definitions.unit`, e.g. `score_0_1`, `rate_per_1000_words`,
 * `share`). Falls back to a plain number for an unrecognized unit rather
 * than throwing -- a future metric with a new unit should still render
 * something reasonable.
 */
export function formatMetricValue(value: number | null, unit: string): string | null {
  if (value === null || Number.isNaN(value)) return null;
  switch (unit) {
    case "score_0_1":
      return value.toFixed(2);
    case "share":
      return `${(value * 100).toFixed(1)}%`;
    case "rate_per_1000_words":
      return `${value >= 0 ? "+" : ""}${value.toFixed(2)} / 1,000 words`;
    default:
      return String(value);
  }
}
