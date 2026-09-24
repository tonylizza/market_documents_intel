import "server-only";
import { z } from "zod";
import { query } from "@/lib/db/pool";
import { MalformedRowError } from "@/lib/db/errors";
import { formatMetricValue } from "@/lib/formatting/numbers";
import { isDiscoveryType, type DiscoveryType } from "@/lib/config/discovery";
import { getFindingCopy } from "@/lib/content/finding-copy";
import type { DiscoveryItem, FinancialConditionCompanyStatus, GovernanceCompanyStatus } from "@/lib/domain/discovery";
import { discoveryItemRowSchema } from "@/lib/schemas/discovery";
import type { DiscoveryItemFilters, DiscoveryRepository } from "@/lib/repositories/discovery-repository";

const availableTypeRowSchema = z.object({ discovery_type: z.string() });

// Track 7F.9: 0.25 per 1,000 words mirrors `findings.CandidateSpec.epsilon`
// for `largest_financial_condition_shift` (financial_condition_topic_change)
// -- kept as a single named constant here since it's shown to the user.
const FINANCIAL_CONDITION_MATERIALITY_THRESHOLD = 0.25;

const financialConditionStatusRowSchema = z.object({
  id: z.string(),
  earlier_period_end: z.string().nullable(),
  later_period_end: z.string().nullable(),
  financial_condition_topic_change: z.number().nullable(),
  report_side_quality: z.string().nullable(),
  report_side_primary_eligible: z.boolean().nullable(),
});

// Track 7F.9: 0.25 per 1,000 words mirrors `findings.CandidateSpec.epsilon`
// for `largest_governance_shift` (governance_topic_change).
const GOVERNANCE_MATERIALITY_THRESHOLD = 0.25;

const governanceStatusRowSchema = z.object({
  id: z.string(),
  earlier_period_end: z.string().nullable(),
  later_period_end: z.string().nullable(),
  governance_topic_change: z.number().nullable(),
  report_side_quality: z.string().nullable(),
  report_side_primary_eligible: z.boolean().nullable(),
});

export class PostgresDiscoveryRepository implements DiscoveryRepository {
  async listAvailableDiscoveryTypes(): Promise<DiscoveryType[]> {
    const rows = await query(`SELECT DISTINCT discovery_type FROM app.current_discovery_items`);
    const types: DiscoveryType[] = [];
    rows.forEach((row, index) => {
      const parsed = availableTypeRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`available-discovery-types[${index}]`, parsed.error.message);
      }
      if (isDiscoveryType(parsed.data.discovery_type)) {
        types.push(parsed.data.discovery_type);
      }
    });
    return types;
  }

  async getDiscoveryItems(filters: DiscoveryItemFilters): Promise<DiscoveryItem[]> {
    const rows = await query(
      `SELECT
         d.id, d.discovery_type, d.rank_scope, d.rank, d.percentile,
         d.company_id, c.ticker AS company_ticker, c.name AS company_name,
         d.report_comparison_id, rc.earlier_period_end, rc.later_period_end,
         d.finding_key, d.supporting_value, d.supporting_unit, d.quality_label
       FROM app.current_discovery_items d
       JOIN app.current_companies c ON c.id = d.company_id
       JOIN app.current_report_comparisons rc ON rc.id = d.report_comparison_id
       WHERE d.discovery_type = $1
         AND d.rank_scope = $2
         AND ($3::text IS NULL OR lower(c.ticker) = lower($3))
         AND ($4::date IS NULL OR rc.later_period_end >= $4)
         AND ($5::date IS NULL OR rc.later_period_end <= $5)
       ORDER BY d.rank`,
      [
        filters.type,
        filters.scope,
        filters.companyTicker ?? null,
        filters.periodStart ?? null,
        filters.periodEnd ?? null,
      ],
    );

    return rows.map((row, index) => {
      const parsed = discoveryItemRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`app.current_discovery_items[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      const copy = getFindingCopy(data.finding_key);
      return {
        id: data.id,
        discoveryType: isDiscoveryType(data.discovery_type) ? data.discovery_type : filters.type,
        rankScope: filters.scope,
        rank: data.rank,
        percentile: data.percentile,
        companyId: data.company_id,
        companyTicker: data.company_ticker,
        companyName: data.company_name,
        reportComparisonId: data.report_comparison_id,
        earlierPeriodEnd: data.earlier_period_end,
        laterPeriodEnd: data.later_period_end,
        findingHeadline: copy.headline,
        supportingValue: data.supporting_value,
        supportingValueDisplay: formatMetricValue(data.supporting_value, data.supporting_unit),
        supportingUnit: data.supporting_unit,
        qualityLabel: data.quality_label,
      } satisfies DiscoveryItem;
    });
  }

  async getFinancialConditionCompanyStatus(companyTicker: string): Promise<FinancialConditionCompanyStatus> {
    const rows = await query(
      `SELECT rc.id, rc.earlier_period_end, rc.later_period_end,
              rc.financial_condition_topic_change,
              rc.report_side_quality, rc.report_side_primary_eligible
       FROM app.current_report_comparisons rc
       JOIN app.current_companies c ON c.id = rc.company_id
       WHERE lower(c.ticker) = lower($1)`,
      [companyTicker],
    );

    if (rows.length === 0) {
      return { status: "no_comparisons" };
    }

    const parsedRows = rows.map((row, index) => {
      const parsed = financialConditionStatusRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`financial-condition-company-status[${index}]`, parsed.error.message);
      }
      return parsed.data;
    });

    const qualityEligible = parsedRows.filter(
      (row) =>
        (row.report_side_quality === "GOOD" || row.report_side_quality === "USABLE") &&
        row.report_side_primary_eligible === true &&
        row.financial_condition_topic_change !== null,
    );

    if (qualityEligible.length === 0) {
      return { status: "failed_quality" };
    }

    const largest = qualityEligible.reduce((max, row) =>
      Math.abs(row.financial_condition_topic_change as number) > Math.abs(max.financial_condition_topic_change as number) ? row : max,
    );

    return {
      status: "below_materiality",
      observedValue: largest.financial_condition_topic_change as number,
      threshold: FINANCIAL_CONDITION_MATERIALITY_THRESHOLD,
      reportComparisonId: largest.id,
      earlierPeriodEnd: largest.earlier_period_end,
      laterPeriodEnd: largest.later_period_end,
    };
  }

  async getGovernanceCompanyStatus(companyTicker: string): Promise<GovernanceCompanyStatus> {
    const rows = await query(
      `SELECT rc.id, rc.earlier_period_end, rc.later_period_end,
              rc.governance_topic_change,
              rc.report_side_quality, rc.report_side_primary_eligible
       FROM app.current_report_comparisons rc
       JOIN app.current_companies c ON c.id = rc.company_id
       WHERE lower(c.ticker) = lower($1)`,
      [companyTicker],
    );

    if (rows.length === 0) {
      return { status: "no_comparisons" };
    }

    const parsedRows = rows.map((row, index) => {
      const parsed = governanceStatusRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`governance-company-status[${index}]`, parsed.error.message);
      }
      return parsed.data;
    });

    const qualityEligible = parsedRows.filter(
      (row) =>
        (row.report_side_quality === "GOOD" || row.report_side_quality === "USABLE") &&
        row.report_side_primary_eligible === true &&
        row.governance_topic_change !== null,
    );

    if (qualityEligible.length === 0) {
      return { status: "failed_quality" };
    }

    const largest = qualityEligible.reduce((max, row) =>
      Math.abs(row.governance_topic_change as number) > Math.abs(max.governance_topic_change as number) ? row : max,
    );

    return {
      status: "below_materiality",
      observedValue: largest.governance_topic_change as number,
      threshold: GOVERNANCE_MATERIALITY_THRESHOLD,
      reportComparisonId: largest.id,
      earlierPeriodEnd: largest.earlier_period_end,
      laterPeriodEnd: largest.later_period_end,
    };
  }
}
