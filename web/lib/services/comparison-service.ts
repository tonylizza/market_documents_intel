import type { ComparisonRepository } from "@/lib/repositories/comparison-repository";
import type {
  DeterministicFinding,
  HeadlineMetric,
  LanguageMetric,
  PassageComposition,
  ReportComparisonDetail,
  TechnicalQualityDetail,
  TopicEvidencePassage,
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
  /** Track 7F.4 item 12 -- top financial_condition subcategory movers
   * (population `financial_condition_subcategory`), kept out of
   * `reportSideLanguageMetrics` since these rows carry raw hit counts, not
   * per-1,000-word rates, and would misrender in that chart/table. */
  financialConditionSubcategoryMovers: LanguageMetric[];
  /** Track 7F.7a.1 item 12 -- top-3 governance subcategory movers by
   * absolute hit-count change, plus each mover's earlier/later governance-
   * share contribution (computed here from the *full* per-side governance-
   * subcategory total, since the repository persists all subcategories
   * with any hits, not just the top 3 -- see `buildGovernanceSubcategoryMovers`). */
  governanceSubcategoryMovers: GovernanceSubcategoryMover[];
  passageComposition: PassageComposition;
  /** Track 7F.9 -- highest-hit eligible passages per topic category and
   * report side (`TOPIC_EVIDENCE_PER_SIDE` each). */
  topicEvidencePassages: TopicEvidencePassage[];
}

export const TOPIC_EVIDENCE_PER_SIDE = 3;

/** Track 7F.7a.1 item 12 -- one governance subcategory mover row, extending
 * the raw `LanguageMetric` hit counts with each side's governance-share
 * contribution (this subcategory's hits / that side's total governance
 * hits across all subcategories, not the M3-G custom-taxonomy-wide share).
 * `litigation`/`shareholder_rights` are flagged `lowVolume` per 7F.7a's
 * "too sparse for standalone interpretation" caution -- corpus-wide, not a
 * per-comparison judgment. */
export interface GovernanceSubcategoryMover {
  id: string;
  subcategory: string | null;
  earlierCount: number;
  laterCount: number;
  change: number;
  earlierShareContribution: number | null;
  laterShareContribution: number | null;
  lowVolume: boolean;
}

const GOVERNANCE_SUBCATEGORY_POPULATION = "governance_subcategory";

/** Corpus-wide sparse governance subcategories (7F.7a section 12) -- flagged
 * for cautionary presentation if surfaced as a mover, never given a
 * standalone materiality claim. */
const GOVERNANCE_LOW_VOLUME_SUBCATEGORIES = new Set(["litigation", "shareholder_rights"]);

export function buildGovernanceSubcategoryMovers(languageMetrics: readonly LanguageMetric[]): GovernanceSubcategoryMover[] {
  const rows = languageMetrics.filter((m) => m.population === GOVERNANCE_SUBCATEGORY_POPULATION);
  const earlierTotal = rows.reduce((sum, r) => sum + (r.earlierCount ?? 0), 0);
  const laterTotal = rows.reduce((sum, r) => sum + (r.laterCount ?? 0), 0);
  return rows
    .map((r) => {
      const earlier = r.earlierCount ?? 0;
      const later = r.laterCount ?? 0;
      return {
        id: r.id,
        subcategory: r.subcategory,
        earlierCount: earlier,
        laterCount: later,
        change: later - earlier,
        earlierShareContribution: earlierTotal > 0 ? earlier / earlierTotal : null,
        laterShareContribution: laterTotal > 0 ? later / laterTotal : null,
        lowVolume: r.subcategory !== null && GOVERNANCE_LOW_VOLUME_SUBCATEGORIES.has(r.subcategory),
      } satisfies GovernanceSubcategoryMover;
    })
    .sort((a, b) => Math.abs(b.change) - Math.abs(a.change))
    .slice(0, 3);
}

/** Track 7F.4 item 12 -- financial_condition subcategory-mover rows persist
 * with this dedicated `population` value (see `publisher.py`'s
 * `LanguageMetric(population="financial_condition_subcategory", ...)`),
 * distinguishing them from the `primary_narrative`/`custom_taxonomy`
 * populations `reportSideLanguageMetrics` renders as rate-based rows. */
const FINANCIAL_CONDITION_SUBCATEGORY_POPULATION = "financial_condition_subcategory";

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
 * composition; plus Track 7F.9's topic-evidence read when topic data exists) -- findings/headline metrics/technical details are all pure
 * derivations of the first, adding zero further queries. `null` when the
 * comparison id doesn't exist (page renders a 404). */
export async function getComparisonPageViewModel(
  repository: ComparisonRepository,
  comparisonId: string,
): Promise<ComparisonPageViewModel | null> {
  const comparison = await repository.getComparisonById(comparisonId);
  if (!comparison) return null;

  const [languageMetrics, passageComposition, topicEvidencePassages] = await Promise.all([
    repository.getComparisonLanguageMetrics(comparisonId),
    repository.getComparisonPassageComposition(comparisonId),
    comparison.topicChange ? repository.getTopicEvidencePassages(comparisonId, TOPIC_EVIDENCE_PER_SIDE) : Promise.resolve([]),
  ]);

  return {
    comparison,
    findings: buildFindings(comparison),
    headlineMetrics: buildHeadlineMetrics(comparison),
    technicalDetails: buildTechnicalDetails(comparison),
    reportSideLanguageMetrics: languageMetrics.filter(
      (m) =>
        m.scope === "report_side" &&
        m.population !== FINANCIAL_CONDITION_SUBCATEGORY_POPULATION &&
        m.population !== GOVERNANCE_SUBCATEGORY_POPULATION,
    ),
    alignmentChangeLanguageMetrics: languageMetrics.filter(
      (m) => m.scope === "alignment_change" && m.population === ALIGNMENT_CHANGE_DEFAULT_POPULATION,
    ),
    financialConditionSubcategoryMovers: languageMetrics.filter(
      (m) => m.population === FINANCIAL_CONDITION_SUBCATEGORY_POPULATION,
    ),
    governanceSubcategoryMovers: buildGovernanceSubcategoryMovers(languageMetrics),
    passageComposition,
    topicEvidencePassages,
  };
}
