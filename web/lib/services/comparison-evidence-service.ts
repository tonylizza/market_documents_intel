import type { AlignmentStatus, ComparisonEvidenceFilters, ComparisonEvidencePage, ComparisonEvidenceSummary } from "@/lib/domain/passage";
import { ALIGNMENT_STATUSES } from "@/lib/config/passage-vocabulary";
import type { ComparisonRepository } from "@/lib/repositories/comparison-repository";
import { buildPaginationState } from "@/lib/services/pagination";

/**
 * Combines two already-existing repository reads (`getComparisonById` +
 * `getComparisonPassageComposition`, both from Milestone 7A.3) into the
 * evidence page's header/summary -- deliberately not a new repository
 * query, since every field it needs is already fetched by those two calls
 * (same "derive, don't re-query" rule as `comparison-service.ts`'s
 * headline metrics). Returns `null` when the comparison itself doesn't
 * exist, so the route can call `notFound()`.
 */
export async function getComparisonEvidenceSummary(
  repository: ComparisonRepository,
  comparisonId: string,
): Promise<ComparisonEvidenceSummary | null> {
  const [comparison, composition] = await Promise.all([
    repository.getComparisonById(comparisonId),
    repository.getComparisonPassageComposition(comparisonId),
  ]);
  if (!comparison) return null;

  const counts = Object.fromEntries(ALIGNMENT_STATUSES.map((status) => [status, 0])) as Record<AlignmentStatus, number>;
  for (const bucket of composition.buckets) {
    counts[bucket.status] = bucket.count;
  }

  return {
    comparisonId: comparison.id,
    companyId: comparison.companyId,
    companyTicker: comparison.companyTicker,
    companyName: comparison.companyName,
    earlierPeriodEnd: comparison.earlierPeriodEnd,
    laterPeriodEnd: comparison.laterPeriodEnd,
    gapMonths: comparison.gapMonths,
    reportSideQuality: comparison.reportSideQuality,
    reportSideQualityLabel: comparison.reportSideQualityLabel,
    alignmentChangeQuality: comparison.alignmentChangeQuality,
    alignmentChangeQualityLabel: comparison.alignmentChangeQualityLabel,
    counts,
    totalCount: composition.totalCount,
  } satisfies ComparisonEvidenceSummary;
}

/** Paginated, filtered evidence rows for one status tab -- two queries
 * (`getComparisonEvidence` + `countComparisonEvidence`, run as
 * `Promise.all`), both scoped to `comparisonId` and never returning rows
 * from another comparison. */
export async function getComparisonEvidencePage(
  repository: ComparisonRepository,
  comparisonId: string,
  filters: ComparisonEvidenceFilters,
): Promise<ComparisonEvidencePage> {
  const [items, totalCount] = await Promise.all([
    repository.getComparisonEvidence(comparisonId, filters),
    repository.countComparisonEvidence(comparisonId, filters),
  ]);

  return {
    items,
    pagination: buildPaginationState(filters.page, filters.pageSize, totalCount),
  } satisfies ComparisonEvidencePage;
}
