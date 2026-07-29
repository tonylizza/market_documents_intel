import type { PassageFilterOptions, PassageSearchParams, PassageSearchPage, PassageSearchResult } from "@/lib/domain/passage";
import type { PassageRepository } from "@/lib/repositories/passage-repository";
import { hasSearchableInput } from "@/lib/services/passage-search-params";
import { buildExcerpt, buildHighlightSpans, extractHighlightTerms } from "@/lib/services/passage-highlight";
import { buildPaginationState } from "@/lib/services/pagination";

function emptyPage(params: PassageSearchParams): PassageSearchPage {
  return {
    results: [],
    pagination: {
      page: 1,
      pageSize: params.pageSize,
      totalCount: 0,
      totalIsCapped: false,
      totalPages: 0,
      hasNextPage: false,
      hasPreviousPage: false,
    },
    params,
  };
}

/**
 * Finalizes one raw repository result into its display form: the
 * repository returns the passage's complete text as a single unmatched
 * span in `excerpt[0]` (a raw carrier, not the final shape) -- this is
 * where it's windowed down to `MAX_EXCERPT_LENGTH` and lexically
 * highlighted against the search terms, and where the heading gets its own
 * highlight spans. Kept in the service (not the repository) so highlighting
 * -- a presentation concern -- never touches SQL.
 */
function finalizeResult(raw: PassageSearchResult, terms: readonly string[]): PassageSearchResult {
  const fullText = raw.excerpt[0]?.text ?? "";
  return {
    ...raw,
    headingHighlight: raw.heading ? buildHighlightSpans(raw.heading, terms) : null,
    excerpt: buildExcerpt(fullText, terms),
  };
}

/**
 * Assembles the full `/passages` view model: filter options are always
 * fetched (the filter panel must render even before a search runs), but
 * the search itself is only executed when `hasSearchableInput` -- a
 * completely empty search never issues the (unbounded) corpus query. Three
 * queries total when a search is active (`searchPassages`,
 * `countPassageSearchResults`, `getPassageFilterOptions`, run as
 * `Promise.all`), one when showing the orientation state.
 */
export async function buildPassageSearchViewModel(
  repository: PassageRepository,
  params: PassageSearchParams,
): Promise<{ page: PassageSearchPage; filterOptions: PassageFilterOptions }> {
  if (!hasSearchableInput(params)) {
    const filterOptions = await repository.getPassageFilterOptions();
    return { page: emptyPage(params), filterOptions };
  }

  const [rawResults, countResult, filterOptions] = await Promise.all([
    repository.searchPassages(params),
    repository.countPassageSearchResults(params),
    repository.getPassageFilterOptions(),
  ]);

  const terms = params.query ? extractHighlightTerms(params.query) : [];
  const results = rawResults.map((result) => finalizeResult(result, terms));
  const pagination = { ...buildPaginationState(params.page, params.pageSize, countResult.count), totalIsCapped: countResult.capped };

  return {
    page: { results, pagination, params },
    filterOptions,
  };
}
