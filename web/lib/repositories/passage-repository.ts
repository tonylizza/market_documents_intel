import type {
  PassageComparisonDetail,
  PassageFilterOptions,
  PassageLanguageSignal,
  PassageSearchParams,
  PassageSearchResult,
} from "@/lib/domain/passage";

/**
 * No generic/arbitrary-query method exists on this interface -- every
 * method is a named, purpose-built read backing one part of `/passages` or
 * `/passages/[passageComparisonId]`. `searchPassages`/`countPassageSearchResults`
 * are deliberately separate queries (never `COUNT(*) OVER()` on every row)
 * so the count can be capped/short-circuited independently of the page
 * fetch -- see `MAX_COUNTED_PASSAGE_RESULTS`.
 */
export interface PassageRepository {
  searchPassages(params: PassageSearchParams): Promise<PassageSearchResult[]>;
  countPassageSearchResults(params: PassageSearchParams): Promise<{ count: number; capped: boolean }>;
  getPassageFilterOptions(): Promise<PassageFilterOptions>;
  getPassageComparisonById(passageComparisonId: string): Promise<PassageComparisonDetail | null>;
  getPassageLanguageSignals(passageComparisonId: string): Promise<PassageLanguageSignal[]>;
}
