import type { ComparisonSummary } from "@/lib/domain/comparison";
import type { ComparisonRow } from "@/lib/schemas/comparison";

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
