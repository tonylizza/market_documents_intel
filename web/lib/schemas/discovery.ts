import { z } from "zod";

export const discoveryItemRowSchema = z.object({
  id: z.string(),
  discovery_type: z.string(),
  rank_scope: z.string(),
  rank: z.number().int(),
  percentile: z.number().nullable(),
  company_id: z.string(),
  company_ticker: z.string(),
  company_name: z.string(),
  report_comparison_id: z.string(),
  earlier_period_end: z.string().nullable(),
  later_period_end: z.string().nullable(),
  finding_key: z.string(),
  supporting_value: z.number(),
  supporting_unit: z.string(),
  quality_label: z.string(),
});

export type DiscoveryItemRow = z.infer<typeof discoveryItemRowSchema>;

export const discoveryFilterOptionsRowSchema = z.object({
  earliest_period_end: z.string().nullable(),
  latest_period_end: z.string().nullable(),
});

export type DiscoveryFilterOptionsRow = z.infer<typeof discoveryFilterOptionsRowSchema>;
