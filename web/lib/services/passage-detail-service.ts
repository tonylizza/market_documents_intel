import type { PassageComparisonDetail, PassageLanguageSignal, TextDiffResult } from "@/lib/domain/passage";
import type { PassageRepository } from "@/lib/repositories/passage-repository";
import { buildTextDiff } from "@/lib/services/passage-diff";

export interface PassageDetailViewModel {
  detail: PassageComparisonDetail;
  languageSignals: PassageLanguageSignal[];
  /** `null` for NEW/REMOVED/one-sided AMBIGUOUS -- a diff needs both sides. */
  diff: TextDiffResult | null;
}

/**
 * Two queries, run as `Promise.all` (`getPassageComparisonById` +
 * `getPassageLanguageSignals`, both scoped to the one `passageComparisonId`
 * -- never a bulk read of the 269,819-row signal table). The diff is
 * computed here, not fetched -- it's a pure, deterministic function over
 * the two already-fetched texts (see `passage-diff.ts`).
 */
export async function getPassageDetailViewModel(
  repository: PassageRepository,
  passageComparisonId: string,
): Promise<PassageDetailViewModel | null> {
  const [detail, languageSignals] = await Promise.all([
    repository.getPassageComparisonById(passageComparisonId),
    repository.getPassageLanguageSignals(passageComparisonId),
  ]);
  if (!detail) return null;

  const diff = detail.earlier && detail.later ? buildTextDiff(detail.earlier.text, detail.later.text) : null;

  return { detail, languageSignals, diff };
}
