import type { HighlightSpan } from "@/lib/domain/passage";
import { MAX_EXCERPT_LENGTH } from "@/lib/domain/passage";

const EXCERPT_CONTEXT_CHARS = 120;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Splits a raw lexical query into individual match terms for TypeScript-side
 * highlighting -- deliberately simpler than `websearch_to_tsquery`'s own
 * parsing (no boolean operators, no stemming): this only drives which
 * *substrings* get visually marked, never search matching itself, so an
 * approximate/literal split is safe and avoids reimplementing Postgres's
 * text-search parser in the browser. */
export function extractHighlightTerms(query: string): string[] {
  const terms = query
    .replace(/"/g, " ")
    .split(/\s+/)
    .map((term) => term.trim())
    .filter((term) => term.length >= 2);
  return Array.from(new Set(terms.map((term) => term.toLowerCase())));
}

/**
 * Splits `text` into a sequence of matched/unmatched spans for safe
 * rendering (e.g. a component maps `matched` spans to `<mark>`) -- never
 * produces an HTML string. Case-insensitive, whole-word-boundary matching
 * only (never a substring match inside an unrelated word).
 */
export function buildHighlightSpans(text: string, terms: readonly string[]): HighlightSpan[] {
  if (terms.length === 0 || text === "") {
    return text === "" ? [] : [{ text, matched: false }];
  }

  const pattern = new RegExp(`\\b(${terms.map(escapeRegExp).join("|")})\\b`, "gi");
  const spans: HighlightSpan[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      spans.push({ text: text.slice(lastIndex, match.index), matched: false });
    }
    spans.push({ text: match[0], matched: true });
    lastIndex = match.index + match[0].length;
    if (match[0].length === 0) pattern.lastIndex += 1;
  }
  if (lastIndex < text.length) {
    spans.push({ text: text.slice(lastIndex), matched: false });
  }
  return spans;
}

/**
 * Builds a bounded excerpt (`MAX_EXCERPT_LENGTH` chars) windowed around the
 * first query-term match, or the leading text when there's no match/no
 * query -- highlighted via `buildHighlightSpans`. Never returns the
 * complete passage text for a long passage; the full text is only shown on
 * `/passages/[passageComparisonId]`.
 */
export function buildExcerpt(text: string, terms: readonly string[], maxLength: number = MAX_EXCERPT_LENGTH): HighlightSpan[] {
  if (text.length <= maxLength) {
    return buildHighlightSpans(text, terms);
  }

  let matchIndex = -1;
  if (terms.length > 0) {
    const pattern = new RegExp(`\\b(?:${terms.map(escapeRegExp).join("|")})\\b`, "i");
    const found = pattern.exec(text);
    matchIndex = found ? found.index : -1;
  }

  let windowStart: number;
  let windowEnd: number;
  if (matchIndex === -1) {
    windowStart = 0;
    windowEnd = maxLength;
  } else {
    windowStart = Math.max(0, matchIndex - EXCERPT_CONTEXT_CHARS);
    windowEnd = Math.min(text.length, windowStart + maxLength);
    windowStart = Math.max(0, windowEnd - maxLength);
  }

  const prefix = windowStart > 0 ? "…" : "";
  const suffix = windowEnd < text.length ? "…" : "";
  const windowed = `${prefix}${text.slice(windowStart, windowEnd)}${suffix}`;
  return buildHighlightSpans(windowed, terms);
}
