import type { ComparisonSummary, TopicCategoryChange, TopicChangeDetail } from "@/lib/domain/comparison";
import type { ComparisonRow, TopicChangeRow } from "@/lib/schemas/comparison";

/**
 * Maps a validated `comparisonRowSchema` row to `ComparisonSummary` --
 * shared by `getCompanyHistory` (array, one company) and
 * `getComparisonById` (single row + company join) so the two queries can
 * never drift into two different field-mapping bugs.
 */
export function mapComparisonRow(data: ComparisonRow): ComparisonSummary {
  return {
    id: data.comparison_id,
    companyId: data.company_id,
    earlierPeriodEnd: data.earlier_period_end,
    laterPeriodEnd: data.later_period_end,
    gapMonths: data.gap_months ?? 0,
    isTransition: data.is_transition ?? false,
    isIrregularGap: data.is_irregular_gap ?? false,
    isLatestForCompany: data.is_latest_for_company ?? false,
    isHistoricalPeakChange: data.is_historical_peak_change ?? false,

    disclosureChangeScore: data.disclosure_change_score,
    disclosureChangeLabel: data.disclosure_change_label,
    disclosureChangePercentile: data.disclosure_change_percentile,
    disclosureChangeQuality: data.disclosure_change_quality,
    disclosureChangeQualityLabel: data.disclosure_change_quality_label,
    disclosureChangePrimaryEligible: data.disclosure_change_primary_eligible,
    disclosureChangeWarning: data.disclosure_change_warning,

    netToneChange: data.net_tone_change,
    netToneChangeLabel: data.net_tone_change_label,
    uncertaintyChange: data.uncertainty_change,
    uncertaintyChangeLabel: data.uncertainty_change_label,
    riskIntroductionRate: data.risk_introduction_rate,
    riskIntroductionLabel: data.risk_introduction_label,
    riskRemovalRate: data.risk_removal_rate,
    riskRemovalLabel: data.risk_removal_label,
    governanceChange: data.governance_change,
    governanceChangeLabel: data.governance_change_label,
    financialConditionChange: data.financial_condition_change,
    financialConditionChangeLabel: data.financial_condition_change_label,
    financialConditionShareChange: data.financial_condition_share_change,
    financialConditionShareChangeLabel: data.financial_condition_share_change_label,
    financialConditionTopicMixChange: data.financial_condition_topic_mix_change,
    governanceShareChange: data.governance_share_change,
    governanceShareChangeLabel: data.governance_share_change_label,
    governanceShareEarlier: data.governance_share_earlier,
    governanceShareLater: data.governance_share_later,
    governanceTopicMixChange: data.governance_topic_mix_change,
    governanceHitsEarlier: data.governance_hits_earlier,
    governanceHitsLater: data.governance_hits_later,
    customTaxonomyHitsEarlier: data.custom_taxonomy_hits_earlier,
    customTaxonomyHitsLater: data.custom_taxonomy_hits_later,

    reportSideQuality: data.report_side_quality,
    reportSideQualityLabel: data.report_side_quality_label,
    reportSidePrimaryEligible: data.report_side_primary_eligible,
    alignmentChangeQuality: data.alignment_change_quality,
    alignmentChangeQualityLabel: data.alignment_change_quality_label,
    alignmentChangePrimaryEligible: data.alignment_change_primary_eligible,

    primaryFindingKey: data.primary_finding_key,
    secondaryFindingKey: data.secondary_finding_key,
    tertiaryFindingKey: data.tertiary_finding_key,
    findingPayload: data.finding_payload,
  } satisfies ComparisonSummary;
}

/** Full column list (aliased to match `comparisonRowSchema`) shared by
 * every query that reads a complete `app.current_report_comparisons` row --
 * keeps the company-history query and the comparison-by-id query from
 * silently drifting apart on which columns they select. */
export const COMPARISON_ROW_COLUMNS_SQL = `
  rc.id AS comparison_id,
  rc.company_id,
  rc.earlier_period_end,
  rc.later_period_end,
  rc.gap_months,
  rc.is_transition,
  rc.is_irregular_gap,
  rc.is_latest_for_company,
  rc.is_historical_peak_change,
  rc.disclosure_change_score,
  rc.disclosure_change_label,
  rc.disclosure_change_percentile,
  rc.disclosure_change_quality,
  rc.disclosure_change_quality_label,
  rc.disclosure_change_primary_eligible,
  rc.disclosure_change_warning,
  rc.net_tone_change,
  rc.net_tone_change_label,
  rc.uncertainty_change,
  rc.uncertainty_change_label,
  rc.risk_introduction_rate,
  rc.risk_introduction_label,
  rc.risk_removal_rate,
  rc.risk_removal_label,
  rc.governance_change,
  rc.governance_change_label,
  rc.financial_condition_change,
  rc.financial_condition_change_label,
  rc.financial_condition_share_change,
  rc.financial_condition_share_change_label,
  rc.financial_condition_topic_mix_change,
  rc.governance_share_change,
  rc.governance_share_change_label,
  rc.governance_share_earlier,
  rc.governance_share_later,
  rc.governance_topic_mix_change,
  rc.governance_hits_earlier,
  rc.governance_hits_later,
  rc.custom_taxonomy_hits_earlier,
  rc.custom_taxonomy_hits_later,
  rc.report_side_quality,
  rc.report_side_quality_label,
  rc.report_side_primary_eligible,
  rc.report_side_warning,
  rc.alignment_change_quality,
  rc.alignment_change_quality_label,
  rc.alignment_change_primary_eligible,
  rc.alignment_change_warning,
  rc.dictionary_match_rate_earlier,
  rc.dictionary_match_rate_later,
  rc.ambiguous_word_share,
  rc.collision_flagged_word_share,
  rc.unmatched_word_share,
  rc.structured_content_exclusion_share,
  rc.primary_finding_key,
  rc.secondary_finding_key,
  rc.tertiary_finding_key,
  rc.finding_payload
`;

/** Track 7F.9 -- topic-change columns, selected only by the comparison-
 * detail query (alongside `COMPARISON_ROW_COLUMNS_SQL`) so the company-
 * history/card queries don't carry them. */
export const TOPIC_CHANGE_COLUMNS_SQL = `
  rc.feature_eligible_primary_words_earlier,
  rc.feature_eligible_primary_words_later,
  rc.financial_condition_hits_earlier,
  rc.financial_condition_hits_later,
  rc.uncertainty_hits_earlier,
  rc.uncertainty_hits_later,
  rc.positive_rate_change,
  rc.negative_rate_change,
  rc.financial_condition_count_change_per_1000,
  rc.financial_condition_topic_change,
  rc.financial_condition_supporting_hits,
  rc.financial_condition_opposing_hits,
  rc.financial_condition_change_consistency_ratio,
  rc.financial_condition_largest_passage_share,
  rc.governance_count_change_per_1000,
  rc.governance_topic_change,
  rc.governance_supporting_hits,
  rc.governance_opposing_hits,
  rc.governance_change_consistency_ratio,
  rc.governance_largest_passage_share,
  rc.uncertainty_count_change_per_1000,
  rc.uncertainty_topic_change,
  rc.uncertainty_supporting_hits,
  rc.uncertainty_opposing_hits,
  rc.uncertainty_change_consistency_ratio,
  rc.uncertainty_largest_passage_share
`;

function mapTopicCategory(
  hitsEarlier: number | null,
  hitsLater: number | null,
  densityChange: number | null,
  row: {
    countChangePer1000: number | null;
    topicChange: number | null;
    supportingHits: number | null;
    opposingHits: number | null;
    changeConsistencyRatio: number | null;
    largestPassageShare: number | null;
  },
): TopicCategoryChange {
  return { hitsEarlier, hitsLater, densityChange, ...row };
}

/** `null` when the publication predates the 7F.9 fields (every topic
 * change column NULL) -- never a fabricated all-zero decomposition. */
export function mapTopicChangeRow(data: TopicChangeRow & ComparisonRow): TopicChangeDetail | null {
  if (
    data.financial_condition_topic_change === null &&
    data.governance_topic_change === null &&
    data.uncertainty_topic_change === null
  ) {
    return null;
  }
  return {
    wordsEarlier: data.feature_eligible_primary_words_earlier,
    wordsLater: data.feature_eligible_primary_words_later,
    positiveRateChange: data.positive_rate_change,
    negativeRateChange: data.negative_rate_change,
    categories: {
      financial_condition: mapTopicCategory(
        data.financial_condition_hits_earlier,
        data.financial_condition_hits_later,
        data.financial_condition_change,
        {
          countChangePer1000: data.financial_condition_count_change_per_1000,
          topicChange: data.financial_condition_topic_change,
          supportingHits: data.financial_condition_supporting_hits,
          opposingHits: data.financial_condition_opposing_hits,
          changeConsistencyRatio: data.financial_condition_change_consistency_ratio,
          largestPassageShare: data.financial_condition_largest_passage_share,
        },
      ),
      governance: mapTopicCategory(data.governance_hits_earlier, data.governance_hits_later, data.governance_change, {
        countChangePer1000: data.governance_count_change_per_1000,
        topicChange: data.governance_topic_change,
        supportingHits: data.governance_supporting_hits,
        opposingHits: data.governance_opposing_hits,
        changeConsistencyRatio: data.governance_change_consistency_ratio,
        largestPassageShare: data.governance_largest_passage_share,
      }),
      uncertainty: mapTopicCategory(data.uncertainty_hits_earlier, data.uncertainty_hits_later, data.uncertainty_change, {
        countChangePer1000: data.uncertainty_count_change_per_1000,
        topicChange: data.uncertainty_topic_change,
        supportingHits: data.uncertainty_supporting_hits,
        opposingHits: data.uncertainty_opposing_hits,
        changeConsistencyRatio: data.uncertainty_change_consistency_ratio,
        largestPassageShare: data.uncertainty_largest_passage_share,
      }),
    },
  };
}
