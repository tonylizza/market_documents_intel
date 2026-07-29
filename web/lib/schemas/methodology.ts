import { z } from "zod";

export const metricDefinitionRowSchema = z.object({
  metric_key: z.string(),
  display_name: z.string(),
  short_description: z.string(),
  technical_description: z.string(),
  unit: z.string(),
  direction_interpretation: z.string(),
  methodology_anchor: z.string(),
});

export type MetricDefinitionRow = z.infer<typeof metricDefinitionRowSchema>;
