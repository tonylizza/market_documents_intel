/**
 * All period-end values arrive as plain `YYYY-MM-DD` strings (see
 * `db/type-parsers.ts` -- Postgres `date` columns are never promoted to a
 * JS `Date`/timezone-aware value). Formatting here parses that string
 * directly rather than going through `Date`, so a report dated
 * 2024-06-30 can never render as 29 June or 1 July depending on the
 * server's local timezone.
 */

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

function parseIsoDate(value: string): { year: number; month: number; day: number } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

export function formatPeriodEnd(value: string | null): string | null {
  if (!value) return null;
  const parsed = parseIsoDate(value);
  if (!parsed) return null;
  return `${parsed.day} ${MONTHS[parsed.month - 1]} ${parsed.year}`;
}

export function formatYear(value: string | null): string | null {
  if (!value) return null;
  const parsed = parseIsoDate(value);
  return parsed ? String(parsed.year) : null;
}

/** e.g. "2016 – 2024", or a single year if the range is a single report. */
export function formatReportRange(first: string | null, last: string | null): string | null {
  const firstYear = formatYear(first);
  const lastYear = formatYear(last);
  if (!firstYear && !lastYear) return null;
  if (firstYear === lastYear || !lastYear) return firstYear;
  if (!firstYear) return lastYear;
  return `${firstYear} – ${lastYear}`;
}

/** e.g. "30 Jun 2023 → 30 Jun 2024" */
export function formatComparisonPeriod(earlier: string | null, later: string | null): string | null {
  const earlierLabel = formatPeriodEnd(earlier);
  const laterLabel = formatPeriodEnd(later);
  if (!earlierLabel && !laterLabel) return null;
  if (!earlierLabel) return laterLabel;
  if (!laterLabel) return earlierLabel;
  return `${earlierLabel} → ${laterLabel}`;
}
