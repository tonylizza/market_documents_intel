import type {
  AlignmentStatus,
  Confidence,
  PassageSearchParams,
  PassageSortKey,
  PassageType,
  ReportSide,
} from "@/lib/domain/passage";
import { DEFAULT_PASSAGE_PAGE_SIZE, MAX_PASSAGE_PAGE_SIZE, MAX_PASSAGE_QUERY_LENGTH, PASSAGE_SORT_KEYS } from "@/lib/domain/passage";
import { ALIGNMENT_STATUSES, CONFIDENCE_LEVELS, PASSAGE_TYPES } from "@/lib/config/passage-vocabulary";

const RAW_QUALITIES = ["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"] as const;
const MAX_FILTER_TOKEN_LENGTH = 64;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export type RawSearchParamsInput = Record<string, string | readonly string[] | undefined>;

function first(raw: RawSearchParamsInput, key: string): string | null {
  const value = raw[key];
  if (value === undefined) return null;
  const single = Array.isArray(value) ? value[0] : value;
  return single === undefined || single === "" ? null : single;
}

function parseBoolean(value: string | null): boolean | null {
  if (value === null) return null;
  if (value === "1" || value === "true") return true;
  if (value === "0" || value === "false") return false;
  return null;
}

function parseEnum<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  if (value === null) return null;
  return (allowed as readonly string[]).includes(value) ? (value as T) : null;
}

function parseToken(value: string | null): string | null {
  if (value === null) return null;
  const trimmed = value.trim().slice(0, MAX_FILTER_TOKEN_LENGTH);
  return trimmed === "" ? null : trimmed;
}

function parseIsoDate(value: string | null): string | null {
  if (value === null) return null;
  return ISO_DATE_PATTERN.test(value) ? value : null;
}

function parseUuid(value: string | null): string | null {
  if (value === null) return null;
  return UUID_PATTERN.test(value) ? value : null;
}

function parsePositiveInt(value: string | null, fallback: number): number {
  if (value === null) return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return fallback;
  return parsed;
}

/**
 * Parses and canonicalizes raw, untrusted `URLSearchParams`-shaped input
 * (Next.js `searchParams`) into a fully validated `PassageSearchParams`.
 * Every field either matches a controlled vocabulary/format or falls back
 * to a safe default -- this function never throws, so a malformed/garbage
 * query string degrades to "no filter applied" rather than a 500.
 */
export function parsePassageSearchParams(raw: RawSearchParamsInput): PassageSearchParams {
  const rawQuery = first(raw, "q");
  const query = rawQuery === null ? null : rawQuery.trim().slice(0, MAX_PASSAGE_QUERY_LENGTH) || null;

  const category = parseToken(first(raw, "category"));
  const subcategory = category ? parseToken(first(raw, "subcategory")) : null;

  const requestedSort = parseEnum<PassageSortKey>(first(raw, "sort"), PASSAGE_SORT_KEYS) ?? "relevance";
  const sort: PassageSortKey = requestedSort === "relevance" && query === null ? "newest_report" : requestedSort;

  const pageSize = Math.min(
    Math.max(parsePositiveInt(first(raw, "pageSize"), DEFAULT_PASSAGE_PAGE_SIZE), 1),
    MAX_PASSAGE_PAGE_SIZE,
  );

  return {
    query,
    exactPhrase: parseBoolean(first(raw, "phrase")) ?? false,
    company: parseToken(first(raw, "company"))?.toUpperCase() ?? null,
    periodStart: parseIsoDate(first(raw, "periodStart")),
    periodEnd: parseIsoDate(first(raw, "periodEnd")),
    comparisonId: parseUuid(first(raw, "comparison")),
    reportSide: parseEnum<ReportSide>(first(raw, "side"), ["EARLIER", "LATER"]),
    alignmentStatus: parseEnum<AlignmentStatus>(first(raw, "status"), ALIGNMENT_STATUSES),
    confidence: parseEnum<Confidence>(first(raw, "confidence"), CONFIDENCE_LEVELS),
    passageType: parseEnum<PassageType>(first(raw, "type"), PASSAGE_TYPES),
    category,
    subcategory,
    reportSideQuality: parseEnum(first(raw, "rsQuality"), RAW_QUALITIES),
    alignmentChangeQuality: parseEnum(first(raw, "acQuality"), RAW_QUALITIES),
    primaryNarrativeEligible: parseBoolean(first(raw, "primary")),
    featureEligible: parseBoolean(first(raw, "feature")),
    irregularGapComparison: parseBoolean(first(raw, "irregularGap")),
    collisionFlag: parseBoolean(first(raw, "collision")),
    splitMergeFlag: parseBoolean(first(raw, "splitMerge")),
    sort,
    page: parsePositiveInt(first(raw, "page"), 1),
    pageSize,
  } satisfies PassageSearchParams;
}

/** `true` when the search has enough input to actually query the
 * database -- a lexical query OR at least one structured filter. Used to
 * show the orientation/empty state instead of an unbounded, filterless
 * corpus dump (`page`/`pageSize`/`sort`/`exactPhrase` alone never count). */
export function hasSearchableInput(params: PassageSearchParams): boolean {
  return (
    params.query !== null ||
    params.company !== null ||
    params.periodStart !== null ||
    params.periodEnd !== null ||
    params.comparisonId !== null ||
    params.reportSide !== null ||
    params.alignmentStatus !== null ||
    params.confidence !== null ||
    params.passageType !== null ||
    params.category !== null ||
    params.reportSideQuality !== null ||
    params.alignmentChangeQuality !== null ||
    params.primaryNarrativeEligible !== null ||
    params.featureEligible !== null ||
    params.irregularGapComparison !== null ||
    params.collisionFlag !== null ||
    params.splitMergeFlag !== null
  );
}

const BOOLEAN_PARAM_KEYS: readonly (keyof PassageSearchParams)[] = [
  "primaryNarrativeEligible",
  "featureEligible",
  "irregularGapComparison",
  "collisionFlag",
  "splitMergeFlag",
];

const BOOLEAN_URL_KEYS: Record<string, string> = {
  primaryNarrativeEligible: "primary",
  featureEligible: "feature",
  irregularGapComparison: "irregularGap",
  collisionFlag: "collision",
  splitMergeFlag: "splitMerge",
};

/** Serializes canonical params back to a compact, shareable query string --
 * default/null values are omitted entirely (never `sort=relevance&page=1`
 * clutter), so `parsePassageSearchParams(new URLSearchParams(serialize(p)))`
 * round-trips to an equivalent `p` for every field that was actually set. */
export function buildPassageSearchQueryString(params: PassageSearchParams): string {
  const entries: [string, string][] = [];
  if (params.query) entries.push(["q", params.query]);
  if (params.exactPhrase) entries.push(["phrase", "1"]);
  if (params.company) entries.push(["company", params.company]);
  if (params.periodStart) entries.push(["periodStart", params.periodStart]);
  if (params.periodEnd) entries.push(["periodEnd", params.periodEnd]);
  if (params.comparisonId) entries.push(["comparison", params.comparisonId]);
  if (params.reportSide) entries.push(["side", params.reportSide]);
  if (params.alignmentStatus) entries.push(["status", params.alignmentStatus]);
  if (params.confidence) entries.push(["confidence", params.confidence]);
  if (params.passageType) entries.push(["type", params.passageType]);
  if (params.category) entries.push(["category", params.category]);
  if (params.subcategory) entries.push(["subcategory", params.subcategory]);
  if (params.reportSideQuality) entries.push(["rsQuality", params.reportSideQuality]);
  if (params.alignmentChangeQuality) entries.push(["acQuality", params.alignmentChangeQuality]);
  for (const key of BOOLEAN_PARAM_KEYS) {
    const value = params[key];
    if (value !== null) entries.push([BOOLEAN_URL_KEYS[key], value ? "1" : "0"]);
  }
  if (params.sort !== "relevance") entries.push(["sort", params.sort]);
  if (params.page !== 1) entries.push(["page", String(params.page)]);
  if (params.pageSize !== DEFAULT_PASSAGE_PAGE_SIZE) entries.push(["pageSize", String(params.pageSize)]);

  const search = new URLSearchParams(entries);
  return search.toString();
}

/** Returns a copy of `params` with `page` reset to `1` -- used whenever any
 * filter/query/sort control changes, per the milestone's URL-state rule
 * ("reset page when filters change"). */
export function resetPage(params: PassageSearchParams): PassageSearchParams {
  return { ...params, page: 1 };
}
