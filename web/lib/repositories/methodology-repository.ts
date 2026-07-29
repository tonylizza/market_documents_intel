import type { MetricDefinition, ApplicationDataSummary } from "@/lib/domain/metric";

export interface MethodologyContentData {
  metrics: MetricDefinition[];
  summary: ApplicationDataSummary;
}

export interface MethodologyRepository {
  getMetricDefinitions(): Promise<MetricDefinition[]>;
  getMethodologyContentData(): Promise<MethodologyContentData>;
}
