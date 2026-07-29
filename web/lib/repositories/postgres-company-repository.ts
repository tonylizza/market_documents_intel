import "server-only";
import { query } from "@/lib/db/pool";
import { MalformedRowError } from "@/lib/db/errors";
import type { Company, CompanyDetail, CompanyHistory } from "@/lib/domain/company";
import type { CompanyCardSummary, ComparisonSummary, DiscoveryItemSummary } from "@/lib/domain/comparison";
import type { ApplicationDataSummary } from "@/lib/domain/metric";
import {
  applicationDataSummaryRowSchema,
  companyCardRowSchema,
  companyRowSchema,
  discoveryItemRowSchema,
  type CompanyCardRow,
} from "@/lib/schemas/company";
import { companyDetailRowSchema, comparisonRowSchema } from "@/lib/schemas/comparison";
import { COMPARISON_ROW_COLUMNS_SQL, mapComparisonRow } from "@/lib/repositories/comparison-mapper";
import { buildDataCoverageNote } from "@/lib/formatting/labels";
import type { CompanyRepository } from "@/lib/repositories/company-repository";

/** Every language-based discovery type currently eligible to be a primary
 * finding -- deliberately excludes `largest_overall_change`/
 * `largest_new_disclosure_share` (feature-quality-gated; empty while the
 * corpus's disclosure-change scores are review-qualified, see
 * docs/frontend.md). Not read from the database: this list encodes which
 * types are *safe to treat as primary* on this page, which is a frontend
 * presentation decision, not a data fact to query for. */
export const LANGUAGE_DISCOVERY_TYPES = [
  "largest_uncertainty_increase",
  "largest_negative_tone_shift",
  "largest_risk_introduction",
  "largest_risk_removal",
  "largest_governance_shift",
  "largest_financial_condition_shift",
] as const;

function mapCompanyRow(row: ReturnType<typeof companyRowSchema.parse>): Company {
  return {
    id: row.id,
    ticker: row.ticker,
    name: row.name,
    sector: row.sector,
    description: row.description,
    firstReportPeriodEnd: row.first_report_period_end,
    latestReportPeriodEnd: row.latest_report_period_end,
    reportCount: row.report_count,
    comparisonCount: row.comparison_count,
    latestComparisonId: row.latest_comparison_id,
    historicalPeakComparisonId: row.historical_peak_comparison_id,
    displayOrder: row.display_order,
    hasCurrentData: row.has_current_data,
  };
}

function mapComparisonFromCardRow(row: CompanyCardRow): ComparisonSummary | null {
  if (!row.comparison_id) return null;
  return {
    id: row.comparison_id,
    companyId: row.company_id,
    earlierPeriodEnd: row.earlier_period_end,
    laterPeriodEnd: row.later_period_end,
    gapMonths: row.gap_months ?? 0,
    isTransition: row.is_transition ?? false,
    isIrregularGap: row.is_irregular_gap ?? false,
    isLatestForCompany: row.is_latest_for_company ?? false,
    isHistoricalPeakChange: row.is_historical_peak_change ?? false,
    disclosureChangeScore: row.disclosure_change_score,
    disclosureChangeLabel: row.disclosure_change_label,
    disclosureChangePercentile: row.disclosure_change_percentile,
    disclosureChangeQuality: row.disclosure_change_quality,
    disclosureChangeQualityLabel: row.disclosure_change_quality_label,
    disclosureChangePrimaryEligible: row.disclosure_change_primary_eligible,
    disclosureChangeWarning: row.disclosure_change_warning,
    netToneChange: row.net_tone_change,
    netToneChangeLabel: row.net_tone_change_label,
    uncertaintyChange: row.uncertainty_change,
    uncertaintyChangeLabel: row.uncertainty_change_label,
    riskIntroductionRate: row.risk_introduction_rate,
    riskIntroductionLabel: row.risk_introduction_label,
    riskRemovalRate: row.risk_removal_rate,
    riskRemovalLabel: row.risk_removal_label,
    governanceChange: row.governance_change,
    governanceChangeLabel: row.governance_change_label,
    financialConditionChange: row.financial_condition_change,
    financialConditionChangeLabel: row.financial_condition_change_label,
    reportSideQuality: row.report_side_quality,
    reportSideQualityLabel: row.report_side_quality_label,
    reportSidePrimaryEligible: row.report_side_primary_eligible,
    alignmentChangeQuality: row.alignment_change_quality,
    alignmentChangeQualityLabel: row.alignment_change_quality_label,
    alignmentChangePrimaryEligible: row.alignment_change_primary_eligible,
    primaryFindingKey: row.primary_finding_key,
    secondaryFindingKey: row.secondary_finding_key,
    tertiaryFindingKey: row.tertiary_finding_key,
    // Not selected by the home-page card query (findings aren't rendered
    // there) -- `null` here is a genuine "not fetched", not "absent".
    findingPayload: null,
  };
}

export class PostgresCompanyRepository implements CompanyRepository {
  async listCompanies(): Promise<Company[]> {
    const rows = await query(
      `SELECT id, ticker, name, sector, description,
              first_report_period_end, latest_report_period_end,
              report_count, comparison_count,
              latest_comparison_id, historical_peak_comparison_id,
              display_order, has_current_data
       FROM app.current_companies
       ORDER BY display_order`,
    );
    return rows.map((row, index) => {
      const parsed = companyRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`app.current_companies[${index}]`, parsed.error.message);
      }
      return mapCompanyRow(parsed.data);
    });
  }

  async getCompanyCardSummaries(): Promise<CompanyCardSummary[]> {
    const rows = await query(
      `SELECT
         c.id AS company_id,
         c.ticker,
         c.name,
         c.sector,
         c.first_report_period_end,
         c.latest_report_period_end,
         c.report_count,
         c.comparison_count,
         c.historical_peak_comparison_id,
         rc.id AS comparison_id,
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
         rc.alignment_change_quality,
         rc.alignment_change_quality_label,
         rc.alignment_change_primary_eligible,
         rc.primary_finding_key,
         rc.secondary_finding_key,
         rc.tertiary_finding_key
       FROM app.current_companies c
       LEFT JOIN app.current_report_comparisons rc
         ON rc.company_id = c.id AND rc.is_latest_for_company = true
       ORDER BY c.display_order`,
    );

    return rows.map((row, index) => {
      const parsed = companyCardRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`company-card-summary[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      return {
        companyId: data.company_id,
        ticker: data.ticker,
        name: data.name,
        sector: data.sector,
        firstReportPeriodEnd: data.first_report_period_end,
        latestReportPeriodEnd: data.latest_report_period_end,
        reportCount: data.report_count,
        comparisonCount: data.comparison_count,
        isHistoricalPeak:
          data.historical_peak_comparison_id !== null && data.historical_peak_comparison_id === data.comparison_id,
        latestComparison: mapComparisonFromCardRow(data),
      } satisfies CompanyCardSummary;
    });
  }

  async getLatestComparisonSummaries(
    discoveryTypes: readonly string[] = LANGUAGE_DISCOVERY_TYPES,
  ): Promise<DiscoveryItemSummary[]> {
    const rows = await query(
      `SELECT
         d.id,
         d.company_id,
         c.ticker,
         c.name,
         d.report_comparison_id,
         d.discovery_type,
         d.rank,
         d.percentile,
         d.supporting_value,
         d.supporting_unit,
         d.quality_label
       FROM app.current_discovery_items d
       JOIN app.current_companies c ON c.id = d.company_id
       WHERE d.rank_scope = 'latest_comparisons'
         AND d.discovery_type = ANY($1::text[])
       ORDER BY d.discovery_type, d.rank`,
      [discoveryTypes as string[]],
    );

    return rows.map((row, index) => {
      const parsed = discoveryItemRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`app.current_discovery_items[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      return {
        id: data.id,
        companyId: data.company_id,
        companyTicker: data.ticker,
        companyName: data.name,
        reportComparisonId: data.report_comparison_id,
        discoveryType: data.discovery_type,
        rank: data.rank,
        percentile: data.percentile,
        supportingValue: data.supporting_value,
        supportingUnit: data.supporting_unit,
        qualityLabel: data.quality_label,
      } satisfies DiscoveryItemSummary;
    });
  }

  async getApplicationDataSummary(): Promise<ApplicationDataSummary> {
    const rows = await query(
      `SELECT
         (SELECT COUNT(*) FROM app.current_companies)::int AS company_count,
         (SELECT COUNT(*) FROM app.current_reports)::int AS report_count,
         (SELECT COUNT(*) FROM app.current_report_comparisons)::int AS comparison_count,
         (SELECT MIN(period_end) FROM app.current_reports) AS earliest_period_end,
         (SELECT MAX(period_end) FROM app.current_reports) AS latest_period_end`,
    );
    const parsed = applicationDataSummaryRowSchema.safeParse(rows[0]);
    if (!parsed.success) {
      throw new MalformedRowError("application-data-summary", parsed.error.message);
    }
    const data = parsed.data;
    return {
      companyCount: data.company_count,
      reportCount: data.report_count,
      comparisonCount: data.comparison_count,
      earliestPeriodEnd: data.earliest_period_end,
      latestPeriodEnd: data.latest_period_end,
      publicationNote: "Data reflects the currently active publication.",
    };
  }

  async getCompanyByTicker(ticker: string): Promise<CompanyDetail | null> {
    const rows = await query(
      `SELECT
         c.id, c.ticker, c.name, c.sector, c.description,
         c.first_report_period_end, c.latest_report_period_end,
         c.report_count, c.comparison_count,
         c.latest_comparison_id, c.historical_peak_comparison_id,
         c.display_order, c.has_current_data,
         rc.report_side_quality AS latest_report_side_quality,
         rc.report_side_quality_label AS latest_report_side_quality_label
       FROM app.current_companies c
       LEFT JOIN app.current_report_comparisons rc ON rc.id = c.latest_comparison_id
       WHERE lower(c.ticker) = lower($1)`,
      [ticker],
    );
    if (rows.length === 0) return null;

    const parsed = companyDetailRowSchema.safeParse(rows[0]);
    if (!parsed.success) {
      throw new MalformedRowError("company-detail", parsed.error.message);
    }
    const data = parsed.data;
    return {
      id: data.id,
      ticker: data.ticker,
      name: data.name,
      sector: data.sector,
      description: data.description,
      firstReportPeriodEnd: data.first_report_period_end,
      latestReportPeriodEnd: data.latest_report_period_end,
      reportCount: data.report_count,
      comparisonCount: data.comparison_count,
      latestComparisonId: data.latest_comparison_id,
      historicalPeakComparisonId: data.historical_peak_comparison_id,
      displayOrder: data.display_order,
      hasCurrentData: data.has_current_data,
      latestReportSideQuality: data.latest_report_side_quality,
      latestReportSideQualityLabel: data.latest_report_side_quality_label,
      dataCoverageNote: buildDataCoverageNote(
        data.report_count,
        data.comparison_count,
        data.first_report_period_end,
        data.latest_report_period_end,
      ),
    } satisfies CompanyDetail;
  }

  async getCompanyHistory(ticker: string): Promise<CompanyHistory | null> {
    const company = await this.getCompanyByTicker(ticker);
    if (!company) return null;

    const rows = await query(
      "SELECT " +
        COMPARISON_ROW_COLUMNS_SQL +
        `
       FROM app.current_report_comparisons rc
       WHERE rc.company_id = $1
       ORDER BY rc.chronological_index`,
      [company.id],
    );

    const comparisons: ComparisonSummary[] = rows.map((row, index) => {
      const parsed = comparisonRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`company-history-comparison[${index}]`, parsed.error.message);
      }
      return mapComparisonRow(parsed.data);
    });

    return { company, comparisons } satisfies CompanyHistory;
  }
}
