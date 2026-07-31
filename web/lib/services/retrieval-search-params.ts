import type { RetrievalMode } from "@/lib/domain/retrieval";
import { RETRIEVAL_MODES } from "@/lib/domain/retrieval";
import type { RawSearchParamsInput } from "@/lib/services/passage-search-params";

/**
 * Parses the `mode` URL parameter (Keyword/Semantic/Hybrid). Deliberately
 * separate from `parsePassageSearchParams` -- every existing lexical-search
 * URL (no `mode` param at all) must keep resolving to the exact same
 * behavior it always has, so this never becomes a field on
 * `PassageSearchParams` itself. An invalid/unknown value falls back to
 * `fallback` (the server-configured default), never throwing.
 */
export function parseRetrievalMode(raw: RawSearchParamsInput, fallback: RetrievalMode): RetrievalMode {
  const value = raw.mode;
  const single = Array.isArray(value) ? value[0] : value;
  if (single && (RETRIEVAL_MODES as readonly string[]).includes(single)) {
    return single as RetrievalMode;
  }
  return fallback;
}

/** Appends/omits `mode` from an existing query string builder -- omitted
 * entirely when it equals `defaultMode`, keeping default-mode URLs exactly
 * as compact as they were before this milestone. */
export function appendRetrievalModeParam(
  queryString: string,
  mode: RetrievalMode,
  defaultMode: RetrievalMode,
): string {
  if (mode === defaultMode) return queryString;
  const params = new URLSearchParams(queryString);
  params.set("mode", mode);
  return params.toString();
}
