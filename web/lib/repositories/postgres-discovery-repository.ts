import "server-only";
import { z } from "zod";
import { query } from "@/lib/db/pool";
import { MalformedRowError } from "@/lib/db/errors";
import { formatMetricValue } from "@/lib/formatting/numbers";
import { isDiscoveryType, type DiscoveryType } from "@/lib/config/discovery";
import { getFindingCopy } from "@/lib/content/finding-copy";
import type { DiscoveryItem } from "@/lib/domain/discovery";
import { discoveryItemRowSchema } from "@/lib/schemas/discovery";
import type { DiscoveryItemFilters, DiscoveryRepository } from "@/lib/repositories/discovery-repository";

const availableTypeRowSchema = z.object({ discovery_type: z.string() });

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
}
