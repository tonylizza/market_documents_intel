import type { AlignmentStatus, ComparisonEvidenceFilters, Confidence } from "@/lib/domain/passage";
import { DEFAULT_PASSAGE_PAGE_SIZE, MAX_PASSAGE_PAGE_SIZE } from "@/lib/domain/passage";
import { ALIGNMENT_STATUSES, CONFIDENCE_LEVELS } from "@/lib/config/passage-vocabulary";
import type { RawSearchParamsInput } from "@/lib/services/passage-search-params";

const MAX_FILTER_TOKEN_LENGTH = 64;

function first(raw: RawSearchParamsInput, key: string): string | null {
  const value = raw[key];
  if (value === undefined) return null;
  const single = Array.isArray(value) ? value[0] : value;
  return single === undefined || single === "" ? null : single;
}

function parseBoolean(value: string | null): boolean | null {
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

function parsePositiveInt(value: string | null, fallback: number): number {
  if (value === null) return fallback;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : fallback;
}

/** Parses `/comparisons/[id]/evidence` query params -- the status tab and
 * every filter live in the URL so they survive pagination/back-forward,
 * per the same shareable-URL rule as `/passages`. */
export function parseComparisonEvidenceFilters(raw: RawSearchParamsInput): ComparisonEvidenceFilters {
  const category = parseToken(first(raw, "category"));
  const pageSize = Math.min(Math.max(parsePositiveInt(first(raw, "pageSize"), DEFAULT_PASSAGE_PAGE_SIZE), 1), MAX_PASSAGE_PAGE_SIZE);

  return {
    status: parseEnum<AlignmentStatus>(first(raw, "status"), ALIGNMENT_STATUSES) ?? "ALL",
    confidence: parseEnum<Confidence>(first(raw, "confidence"), CONFIDENCE_LEVELS),
    category,
    subcategory: category ? parseToken(first(raw, "subcategory")) : null,
    collisionFlag: parseBoolean(first(raw, "collision")),
    splitMergeFlag: parseBoolean(first(raw, "splitMerge")),
    hasHeading: parseBoolean(first(raw, "heading")),
    pageStart: (() => {
      const value = parsePositiveInt(first(raw, "pageStart"), 0);
      return value >= 1 ? value : null;
    })(),
    pageEnd: (() => {
      const value = parsePositiveInt(first(raw, "pageEnd"), 0);
      return value >= 1 ? value : null;
    })(),
    page: parsePositiveInt(first(raw, "page"), 1),
    pageSize,
  } satisfies ComparisonEvidenceFilters;
}

/** Serializes evidence filters back to a compact, shareable query string --
 * mirrors `buildPassageSearchQueryString`'s "omit defaults" rule. */
export function buildComparisonEvidenceQueryString(filters: ComparisonEvidenceFilters): string {
  const entries: [string, string][] = [];
  if (filters.status !== "ALL") entries.push(["status", filters.status]);
  if (filters.confidence) entries.push(["confidence", filters.confidence]);
  if (filters.category) entries.push(["category", filters.category]);
  if (filters.subcategory) entries.push(["subcategory", filters.subcategory]);
  if (filters.collisionFlag !== null) entries.push(["collision", filters.collisionFlag ? "1" : "0"]);
  if (filters.splitMergeFlag !== null) entries.push(["splitMerge", filters.splitMergeFlag ? "1" : "0"]);
  if (filters.hasHeading !== null) entries.push(["heading", filters.hasHeading ? "1" : "0"]);
  if (filters.pageStart !== null) entries.push(["pageStart", String(filters.pageStart)]);
  if (filters.pageEnd !== null) entries.push(["pageEnd", String(filters.pageEnd)]);
  if (filters.page !== 1) entries.push(["page", String(filters.page)]);
  if (filters.pageSize !== DEFAULT_PASSAGE_PAGE_SIZE) entries.push(["pageSize", String(filters.pageSize)]);
  return new URLSearchParams(entries).toString();
}

export function resetEvidencePage(filters: ComparisonEvidenceFilters): ComparisonEvidenceFilters {
  return { ...filters, page: 1 };
}
