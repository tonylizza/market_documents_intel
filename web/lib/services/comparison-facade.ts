import type { ComparisonRepository } from "@/lib/repositories/comparison-repository";
import { type ComparisonPageViewModel, getComparisonPageViewModel } from "@/lib/services/comparison-service";
import type { NarrativeUnitComparison, StructuredTableComparison } from "@/lib/domain/cutover-comparison";
import { isCutoverEnabled } from "@/lib/config/cutover";

/**
 * Track 7A.3/7A.4: the single comparison facade the live caller (the
 * comparison detail page) reads from -- it never knows whether a comparison
 * is served by the legacy passage-alignment pipeline or the Track 7C.6
 * semantic-unit/structured-table pipeline; it only branches on
 * `ComparisonView.backend` for display (docs/7a3-7a4-live-comparison-
 * integration.md, "Integration principle").
 *
 * `narrative`/`structured` are NOT mutually exclusive: the fixed 7C.6 scope
 * covers ACT for both a narrative unit (`cfo_conclusion`) and two
 * structured table families at once, so a single ACT report comparison can
 * carry both simultaneously (this was verified against the real local
 * dataset during 7A.3/7A.4 local end-to-end testing -- an earlier
 * discriminated-union design that only ever picked one silently dropped
 * ACT's structured tables). `backend` stays a simple
 * "did the new pipeline contribute anything to this comparison" signal for
 * observability; the page renders each payload independently of the other.
 *
 * `legacy` is always populated (even when narrative/structured are present)
 * as diagnostic/audit context -- it must never be shown as the *primary*
 * result for a unit/table the new pipeline covers, including when `status`
 * is unresolved. That guarantee is enforced by construction here, not by
 * page code remembering to check `status`: this function is the only place
 * that decides whether the new pipeline "covers" this comparison, and it
 * decides purely from whether a cutover row exists -- never from that row's
 * `status`.
 */
export type ComparisonView =
  | { backend: "LEGACY_PASSAGE"; legacy: ComparisonPageViewModel }
  | {
      backend: "CUTOVER";
      narrative: NarrativeUnitComparison | null;
      structured: StructuredTableComparison[];
      legacy: ComparisonPageViewModel;
    };

export async function getComparisonView(
  repository: ComparisonRepository,
  comparisonId: string,
): Promise<ComparisonView | null> {
  const legacy = await getComparisonPageViewModel(repository, comparisonId);
  if (!legacy) return null;

  if (!isCutoverEnabled()) {
    return { backend: "LEGACY_PASSAGE", legacy };
  }

  const [narrative, structured] = await Promise.all([
    repository.getNarrativeUnitComparison(comparisonId),
    repository.getStructuredTableComparisons(comparisonId),
  ]);

  if (narrative || structured.length > 0) {
    return { backend: "CUTOVER", narrative, structured, legacy };
  }
  return { backend: "LEGACY_PASSAGE", legacy };
}
