export interface MetricDefinition {
  metricKey: string;
  displayName: string;
  shortDescription: string;
  technicalDescription: string;
  unit: string;
  directionInterpretation: string;
  methodologyAnchor: string;
}

export interface ApplicationDataSummary {
  companyCount: number;
  reportCount: number;
  comparisonCount: number;
  earliestPeriodEnd: string | null;
  latestPeriodEnd: string | null;
  /** Static note, not a live timestamp -- `app.current_*` views don't expose
   * `publication_version`/`activated_at` (both live only in
   * `app_internal.publications`, which the read-only role cannot reach).
   * See docs/frontend.md. */
  publicationNote: string;
}
