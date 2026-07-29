import type { LanguageMetric, PassageComposition, ReportComparisonDetail } from "@/lib/domain/comparison";
import type { ComparisonEvidenceFilterOptions, ComparisonEvidenceFilters, ComparisonEvidenceItem } from "@/lib/domain/passage";

/**
 * No generic/arbitrary-query method exists on this interface by design --
 * every method here is a named, purpose-built read for the comparison
 * detail page. Headline metrics, deterministic findings, and technical
 * details are deliberately *not* separate repository methods: they're all
 * derivable from the single `ReportComparisonDetail` row already returned
 * by `getComparisonById`, so deriving them in `comparison-service.ts`
 * (pure, unit-testable functions) avoids re-querying the same row three
 * more times -- see docs/frontend.md's repository/service split.
 */
export interface ComparisonRepository {
  getComparisonById(comparisonId: string): Promise<ReportComparisonDetail | null>;
  getComparisonLanguageMetrics(comparisonId: string): Promise<LanguageMetric[]>;
  getComparisonPassageComposition(comparisonId: string): Promise<PassageComposition>;

  /** Bounded, filtered, paginated evidence rows for one comparison -- see
   * `passage-mapper.ts`'s shared column list. Never fetches every alignment
   * for a comparison at once. */
  getComparisonEvidence(comparisonId: string, filters: ComparisonEvidenceFilters): Promise<ComparisonEvidenceItem[]>;
  countComparisonEvidence(comparisonId: string, filters: ComparisonEvidenceFilters): Promise<number>;
  getComparisonEvidenceFilterOptions(comparisonId: string): Promise<ComparisonEvidenceFilterOptions>;
}
