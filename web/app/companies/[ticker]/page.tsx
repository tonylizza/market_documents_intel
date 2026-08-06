import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import {
  buildComparisonPreview,
  getCompanyHistoricalHighlights,
  getCompanyMetricSeries,
  resolveSelectedComparison,
} from "@/lib/services/company-history-service";
import { COMPARISON_METRICS, resolveComparisonMetricKey } from "@/lib/config/comparison";
import { PageHeader } from "@/components/PageHeader";
import { SectionHeader } from "@/components/SectionHeader";
import { QualityBadge } from "@/components/QualityBadge";
import { FullHistoryChart } from "@/components/FullHistoryChart";
import { MetricSelector } from "@/components/MetricSelector";
import { AdaptiveComparisonNavigator } from "@/components/AdaptiveComparisonNavigator";
import { ComparisonPreviewSection } from "@/components/ComparisonPreviewSection";
import { formatReportRange } from "@/lib/formatting/dates";
import { formatCount } from "@/lib/formatting/numbers";
import styles from "./page.module.css";

interface CompanyPageProps {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ comparison?: string; metric?: string }>;
}

export async function generateMetadata({ params }: CompanyPageProps): Promise<Metadata> {
  const { ticker } = await params;
  return { title: ticker.toUpperCase() };
}

/**
 * Full company detail page (Milestone 7A.3): header, full-history chart
 * with a bounded metric selector, the adaptive comparison navigator, and a
 * compact preview of the URL-selected comparison. Two queries total
 * (`getCompanyHistory`'s company row + full comparison list) -- everything
 * else (metric series, highlights, findings, headline metrics) is derived
 * in-memory.
 */
export default async function CompanyPage({ params, searchParams }: CompanyPageProps) {
  const { ticker } = await params;
  const { comparison: comparisonParam, metric: metricParam } = await searchParams;
  const repository = new PostgresCompanyRepository();

  // Deliberately not caught here -- letting DB failures propagate lets
  // error.tsx render the friendly fallback instead of duplicating that
  // logic inline.
  const history = await repository.getCompanyHistory(ticker);

  if (!history) {
    notFound();
  }

  const { company, comparisons } = history;
  const metricKey = resolveComparisonMetricKey(metricParam);
  const metricConfig = COMPARISON_METRICS[metricKey];
  const metricSeries = getCompanyMetricSeries(comparisons, metricKey);
  const highlights = getCompanyHistoricalHighlights(comparisons);
  const selectedComparison = resolveSelectedComparison(comparisons, comparisonParam ?? null);
  const preview = selectedComparison ? buildComparisonPreview(selectedComparison) : null;
  const reportRange = formatReportRange(company.firstReportPeriodEnd, company.latestReportPeriodEnd);

  return (
    <>
      <PageHeader title={company.name} subtitle={company.ticker}>
        <QualityBadge
          dimension="report-side"
          quality={company.latestReportSideQuality}
          label={company.latestReportSideQualityLabel}
        />
      </PageHeader>

      <dl className={styles.meta}>
        <div>
          <dt>Report range</dt>
          <dd>{reportRange ?? "—"}</dd>
        </div>
        <div>
          <dt>Reports</dt>
          <dd>{formatCount(company.reportCount)}</dd>
        </div>
        <div>
          <dt>Comparisons</dt>
          <dd>{formatCount(company.comparisonCount)}</dd>
        </div>
      </dl>
      <p className={styles.coverageNote}>{company.dataCoverageNote}</p>

      <section aria-labelledby="history-heading" className={styles.section}>
        <SectionHeader
          id="history-heading"
          title="Full-history overview"
          description="Disclosure-change magnitude is exploratory in the current corpus (Review recommended) and is shown for exploration, not as a validated primary ranking. Switch metrics below."
        />
        <MetricSelector selected={metricKey} />
        <FullHistoryChart points={metricSeries} metric={metricConfig} />
      </section>

      <section aria-labelledby="navigator-heading" className={styles.section}>
        <SectionHeader id="navigator-heading" title="Comparison history" description="Select a comparison to preview it below." />
        <AdaptiveComparisonNavigator
          comparisons={comparisons}
          companyTicker={company.ticker}
          selectedComparisonId={selectedComparison?.id ?? null}
          highlights={highlights}
        />
      </section>

      {preview && (
        <section aria-labelledby="preview-heading" className={styles.section}>
          <SectionHeader id="preview-heading" title="Selected comparison" />
          <ComparisonPreviewSection preview={preview} />
        </section>
      )}
    </>
  );
}
