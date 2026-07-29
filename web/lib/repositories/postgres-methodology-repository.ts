import "server-only";
import { z } from "zod";
import { query } from "@/lib/db/pool";
import { MalformedRowError } from "@/lib/db/errors";
import type { MetricDefinition, ApplicationDataSummary } from "@/lib/domain/metric";
import { applicationDataSummaryRowSchema } from "@/lib/schemas/company";
import { metricDefinitionRowSchema } from "@/lib/schemas/methodology";
import type { MethodologyContentData, MethodologyRepository } from "@/lib/repositories/methodology-repository";

const activePublicationRowSchema = z.object({ publication_id: z.string() });

/**
 * `app.metric_definitions`/`app.metric_label_thresholds` have no
 * `current_*` view wrapper (unlike every other app table) -- both remain
 * publication-scoped, so every read here resolves the active
 * `publication_id` first (via an already-current-filtered view) and
 * filters explicitly. Never reads these two tables unfiltered, which would
 * mix in stale/historical publications' rows. See docs/frontend.md.
 */
async function resolveActivePublicationId(): Promise<string | null> {
  const rows = await query(`SELECT publication_id FROM app.current_companies LIMIT 1`);
  if (rows.length === 0) return null;
  const parsed = activePublicationRowSchema.safeParse(rows[0]);
  if (!parsed.success) {
    throw new MalformedRowError("active-publication-id", parsed.error.message);
  }
  return parsed.data.publication_id;
}

export class PostgresMethodologyRepository implements MethodologyRepository {
  async getMetricDefinitions(): Promise<MetricDefinition[]> {
    const publicationId = await resolveActivePublicationId();
    if (!publicationId) return [];

    const rows = await query(
      `SELECT metric_key, display_name, short_description, technical_description,
              unit, direction_interpretation, methodology_anchor
       FROM app.metric_definitions
       WHERE publication_id = $1
       ORDER BY display_name`,
      [publicationId],
    );

    return rows.map((row, index) => {
      const parsed = metricDefinitionRowSchema.safeParse(row);
      if (!parsed.success) {
        throw new MalformedRowError(`app.metric_definitions[${index}]`, parsed.error.message);
      }
      const data = parsed.data;
      return {
        metricKey: data.metric_key,
        displayName: data.display_name,
        shortDescription: data.short_description,
        technicalDescription: data.technical_description,
        unit: data.unit,
        directionInterpretation: data.direction_interpretation,
        methodologyAnchor: data.methodology_anchor,
      } satisfies MetricDefinition;
    });
  }

  private async getApplicationDataSummary(): Promise<ApplicationDataSummary> {
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

  async getMethodologyContentData(): Promise<MethodologyContentData> {
    const [metrics, summary] = await Promise.all([this.getMetricDefinitions(), this.getApplicationDataSummary()]);
    return { metrics, summary };
  }
}
