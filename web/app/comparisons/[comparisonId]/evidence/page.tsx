import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PostgresComparisonRepository } from "@/lib/repositories/postgres-comparison-repository";
import { getComparisonEvidencePage, getComparisonEvidenceSummary } from "@/lib/services/comparison-evidence-service";
import { parseComparisonEvidenceFilters } from "@/lib/services/comparison-evidence-params";
import type { RawSearchParamsInput } from "@/lib/services/passage-search-params";
import { PageHeader } from "@/components/PageHeader";
import { SectionHeader } from "@/components/SectionHeader";
import { ErrorState } from "@/components/ErrorState";
import { QualityBadge } from "@/components/QualityBadge";
import { ComparisonEvidenceSummarySection } from "@/components/ComparisonEvidenceSummarySection";
import { ComparisonEvidenceStatusTabs } from "@/components/ComparisonEvidenceStatusTabs";
import { ComparisonEvidenceFiltersForm } from "@/components/ComparisonEvidenceFiltersForm";
import { ComparisonEvidenceResultsList } from "@/components/ComparisonEvidenceResultsList";
import { formatComparisonPeriod } from "@/lib/formatting/dates";
import styles from "./page.module.css";

interface EvidencePageProps {
  params: Promise<{ comparisonId: string }>;
  searchParams: Promise<RawSearchParamsInput>;
}

export async function generateMetadata({ params }: EvidencePageProps): Promise<Metadata> {
  const { comparisonId } = await params;
  const repository = new PostgresComparisonRepository();
  try {
    const summary = await getComparisonEvidenceSummary(repository, comparisonId);
    if (!summary) return { title: "Evidence not found" };
    return { title: `${summary.companyTicker} evidence` };
  } catch {
    return { title: "Comparison evidence" };
  }
}

/** Comparison-specific passage evidence (Milestone 7A.4). Header + summary
 * reuse two existing `ComparisonRepository` queries (no new SQL); the
 * filtered/paginated evidence list is two additional, comparison-scoped
 * queries -- never every alignment for the comparison at once. */
export default async function ComparisonEvidencePage({ params, searchParams }: EvidencePageProps) {
  const { comparisonId } = await params;
  const rawFilters = await searchParams;
  const filters = parseComparisonEvidenceFilters(rawFilters);
  const repository = new PostgresComparisonRepository();

  let summary: Awaited<ReturnType<typeof getComparisonEvidenceSummary>> = null;
  let failed = false;
  try {
    summary = await getComparisonEvidenceSummary(repository, comparisonId);
  } catch (error) {
    failed = true;
    console.error("Failed to load comparison evidence summary:", (error as Error).message);
  }

  if (failed) {
    return <ErrorState title="Comparison evidence is temporarily unavailable" />;
  }
  if (!summary) {
    notFound();
  }

  let evidencePage: Awaited<ReturnType<typeof getComparisonEvidencePage>> | null = null;
  let evidenceFailed = false;
  let filterOptions: Awaited<ReturnType<typeof repository.getComparisonEvidenceFilterOptions>> | null = null;
  try {
    [evidencePage, filterOptions] = await Promise.all([
      getComparisonEvidencePage(repository, comparisonId, filters),
      repository.getComparisonEvidenceFilterOptions(comparisonId),
    ]);
  } catch (error) {
    evidenceFailed = true;
    console.error("Failed to load comparison evidence rows:", (error as Error).message);
  }

  return (
    <>
      <p className={styles.backlink}>
        <Link href={`/comparisons/${comparisonId}`}>← Back to comparison summary</Link>
      </p>

      <PageHeader
        title={`${formatComparisonPeriod(summary.earlierPeriodEnd, summary.laterPeriodEnd) ?? "Unknown period"}`}
        subtitle={`${summary.companyName} (${summary.companyTicker}) -- passage evidence`}
        description={`Reporting gap: ${summary.gapMonths} months.`}
      >
        <div className={styles.qualityRow}>
          <QualityBadge dimension="report-side" quality={summary.reportSideQuality} label={summary.reportSideQualityLabel} compact />
          <QualityBadge dimension="alignment-change" quality={summary.alignmentChangeQuality} label={summary.alignmentChangeQualityLabel} compact />
        </div>
      </PageHeader>

      <section aria-labelledby="evidence-summary-heading" className={styles.section}>
        <SectionHeader id="evidence-summary-heading" title="Evidence summary" />
        <ComparisonEvidenceSummarySection summary={summary} />
      </section>

      <section aria-label="Evidence status" className={styles.section}>
        <ComparisonEvidenceStatusTabs comparisonId={comparisonId} filters={filters} summary={summary} />
      </section>

      <section aria-labelledby="evidence-results-heading" className={styles.section}>
        <h2 id="evidence-results-heading" className="visually-hidden">
          Evidence results
        </h2>
        {evidenceFailed || !evidencePage || !filterOptions ? (
          <ErrorState title="Evidence results are temporarily unavailable" />
        ) : (
          <>
            <ComparisonEvidenceFiltersForm comparisonId={comparisonId} filters={filters} filterOptions={filterOptions} />
            <ComparisonEvidenceResultsList comparisonId={comparisonId} page={evidencePage} filters={filters} />
          </>
        )}
      </section>
    </>
  );
}
