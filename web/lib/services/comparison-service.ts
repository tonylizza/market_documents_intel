import type { ComparisonRepository } from "@/lib/repositories/comparison-repository";
import type {
  DeterministicFinding,
  HeadlineMetric,
  LanguageMetric,
  PassageComposition,
  ReportComparisonDetail,
  TechnicalQualityDetail,
} from "@/lib/domain/comparison";
import { buildFindings } from "@/lib/content/finding-copy";
import { buildHeadlineMetrics } from "@/lib/services/headline-metrics";

export interface ComparisonPageViewModel {
  comparison: ReportComparisonDetail;
  findings: DeterministicFinding[];
  headlineMetrics: HeadlineMetric[];
  technicalDetails: TechnicalQualityDetail;
  reportSideLanguageMetrics: LanguageMetric[];
  alignmentChangeLanguageMetrics: LanguageMetric[];
  passageComposition: PassageComposition;
}

/** Derived purely from the already-fetched comparison row -- zero
 * additional queries. */
export function buildTechnicalDetails(comparison: ReportComparisonDetail): TechnicalQualityDetail {
  return {
    dictionaryMatchRateEarlier: comparison.dictionaryMatchRateEarlier,
    dictionaryMatchRateLater: comparison.dictionaryMatchRateLater,
    ambiguousWordShare: comparison.ambiguousWordShare,
    collisionFlaggedWordShare: comparison.collisionFlaggedWordShare,
    unmatchedWordShare: comparison.unmatchedWordShare,
    structuredContentExclusionShare: comparison.structuredContentExclusionShare,
    reportSidePrimaryEligible: comparison.reportSidePrimaryEligible,
    alignmentChangePrimaryEligible: comparison.alignmentChangePrimaryEligible,
    disclosureChangePrimaryEligible: comparison.disclosureChangePrimaryEligible,
    reportSideWarning: comparison.reportSideWarning,
    alignmentChangeWarning: comparison.alignmentChangeWarning,
    disclosureChangeWarning: comparison.disclosureChangeWarning,
  };
}

/** Alignment-dependent language metrics default population -- excludes
 * ambiguous passages, per the milestone's "alignment-change behavior"
 * requirement (never implies strong attribution from an ambiguous-inclusive
 * population). */
const ALIGNMENT_CHANGE_DEFAULT_POPULATION = "primary_narrative_excl_ambiguous";

/** Three queries total (comparison+company join, language metrics, passage
 * composition) -- findings/headline metrics/technical details are all pure
 * derivations of the first, adding zero further queries. `null` when the
 * comparison id doesn't exist (page renders a 404). */
export async function getComparisonPageViewModel(
  repository: ComparisonRepository,
  comparisonId: string,
): Promise<ComparisonPageViewModel | null> {
  const comparison = await repository.getComparisonById(comparisonId);
  if (!comparison) return null;

  const [languageMetrics, passageComposition] = await Promise.all([
    repository.getComparisonLanguageMetrics(comparisonId),
    repository.getComparisonPassageComposition(comparisonId),
  ]);

  return {
    comparison,
    findings: buildFindings(comparison),
    headlineMetrics: buildHeadlineMetrics(comparison),
    technicalDetails: buildTechnicalDetails(comparison),
    reportSideLanguageMetrics: languageMetrics.filter((m) => m.scope === "report_side"),
    alignmentChangeLanguageMetrics: languageMetrics.filter(
      (m) => m.scope === "alignment_change" && m.population === ALIGNMENT_CHANGE_DEFAULT_POPULATION,
    ),
    passageComposition,
  };
}
