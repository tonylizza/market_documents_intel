import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PostgresComparisonRepository } from "@/lib/repositories/postgres-comparison-repository";
import { getComparisonPageViewModel } from "@/lib/services/comparison-service";
import { PageHeader } from "@/components/PageHeader";
import { SectionHeader } from "@/components/SectionHeader";
import { ErrorState } from "@/components/ErrorState";
import { QualityBadge } from "@/components/QualityBadge";
import { DisclosureChangeSummary } from "@/components/DisclosureChangeSummary";
import { HeadlineMetricCard } from "@/components/HeadlineMetricCard";
import { DeterministicFindingsList } from "@/components/DeterministicFindingsList";
import { LanguageMetricsSection } from "@/components/LanguageMetricsSection";
import { PassageCompositionSection } from "@/components/PassageCompositionSection";
import { TechnicalDetails } from "@/components/TechnicalDetails";
import { DefinitionList } from "@/components/DefinitionList";
import { formatPeriodEnd } from "@/lib/formatting/dates";
import { formatCount, formatMetricValue } from "@/lib/formatting/numbers";
import styles from "./page.module.css";

interface ComparisonPageProps {
  params: Promise<{ comparisonId: string }>;
}

export async function generateMetadata({ params }: ComparisonPageProps): Promise<Metadata> {
  const { comparisonId } = await params;
  const repository = new PostgresComparisonRepository();
  try {
    const comparison = await repository.getComparisonById(comparisonId);
    if (!comparison) return { title: "Comparison not found" };
    return { title: `${comparison.companyTicker} comparison` };
  } catch {
    return { title: "Comparison" };
  }
}

/**
 * Report-comparison detail page (Milestone 7A.3): the primary analytical
 * page. Three queries total via `getComparisonPageViewModel` -- findings,
 * headline metrics, and technical details are all derived from the first
 * query's row, not fetched separately.
 */
export default async function ComparisonPage({ params }: ComparisonPageProps) {
  const { comparisonId } = await params;
  const repository = new PostgresComparisonRepository();

  let viewModel: Awaited<ReturnType<typeof getComparisonPageViewModel>> = null;
  let failed = false;
  try {
    viewModel = await getComparisonPageViewModel(repository, comparisonId);
  } catch (error) {
    failed = true;
    console.error("Failed to load comparison page data:", (error as Error).message);
  }

  if (failed) {
    return <ErrorState title="This comparison is temporarily unavailable" />;
  }
  if (!viewModel) {
    notFound();
  }

  const { comparison, findings, headlineMetrics, technicalDetails, reportSideLanguageMetrics, alignmentChangeLanguageMetrics, passageComposition } =
    viewModel;

  return (
    <>
      <p className={styles.backlink}>
        <Link href={`/companies/${comparison.companyTicker}`}>← {comparison.companyName} history</Link>
      </p>

      <PageHeader
        title={`${formatPeriodEnd(comparison.earlierPeriodEnd) ?? "Unknown"} → ${formatPeriodEnd(comparison.laterPeriodEnd) ?? "Unknown"}`}
        subtitle={`${comparison.companyName} (${comparison.companyTicker})`}
        description={`Reporting gap: ${comparison.gapMonths} months${comparison.isTransition ? " — transition report" : ""}${comparison.isIrregularGap ? " — irregular gap" : ""}`}
      />

      <section aria-labelledby="quality-heading" className={styles.section}>
        <SectionHeader id="quality-heading" title="Quality summary" description="Three independent quality dimensions -- never merged into one score." />
        <div className={styles.qualityGrid}>
          <QualityBadge dimension="report-side" quality={comparison.reportSideQuality} label={comparison.reportSideQualityLabel} />
          <QualityBadge
            dimension="alignment-change"
            quality={comparison.alignmentChangeQuality}
            label={comparison.alignmentChangeQualityLabel}
          />
          <DisclosureChangeSummary
            score={comparison.disclosureChangeScore}
            label={comparison.disclosureChangeLabel}
            quality={comparison.disclosureChangeQuality}
            qualityLabel={comparison.disclosureChangeQualityLabel}
          />
        </div>
      </section>

      <section aria-labelledby="metrics-heading" className={styles.section}>
        <SectionHeader id="metrics-heading" title="Headline metrics" />
        <div className={styles.metricGrid}>
          {headlineMetrics.map((metric) => (
            <HeadlineMetricCard metric={metric} key={metric.metricKey} />
          ))}
        </div>
      </section>

      <section aria-labelledby="findings-heading" className={styles.section}>
        <SectionHeader id="findings-heading" title="Deterministic findings" />
        <DeterministicFindingsList findings={findings} />
      </section>

      <section aria-labelledby="report-language-heading" className={styles.section}>
        <SectionHeader
          id="report-language-heading"
          title="Report-level language changes"
          description="Whole-report language rates, earlier report vs. later report."
        />
        <LanguageMetricsSection metrics={reportSideLanguageMetrics} variant="report-side" />
      </section>

      <section aria-labelledby="alignment-language-heading" className={styles.section}>
        <SectionHeader
          id="alignment-language-heading"
          title="Alignment-dependent language changes"
          description="Depends on passage-level attribution between the two reports; excludes ambiguous passages. Attribution strength is shown above under Alignment-change quality -- a Usable attribution or Attribution uncertain result should not be read as strong attribution."
        />
        <LanguageMetricsSection metrics={alignmentChangeLanguageMetrics} variant="alignment-change" />
      </section>

      <section aria-labelledby="passage-composition-heading" className={styles.section}>
        <SectionHeader id="passage-composition-heading" title="Passage-composition summary" />
        <PassageCompositionSection composition={passageComposition} />
        <p className={styles.futureCallout}>
          <Link href={`/comparisons/${comparison.id}/evidence`}>Explore passage evidence for this comparison →</Link>
        </p>
      </section>

      <section aria-labelledby="technical-heading" className={styles.section}>
        <SectionHeader id="technical-heading" title="Technical details" />
        <TechnicalDetails summary="Show technical details">
          <DefinitionList
            items={[
              { term: "Dictionary match rate (earlier)", description: formatMetricValue(technicalDetails.dictionaryMatchRateEarlier, "share") ?? "Not available" },
              { term: "Dictionary match rate (later)", description: formatMetricValue(technicalDetails.dictionaryMatchRateLater, "share") ?? "Not available" },
              { term: "Ambiguous word share", description: formatMetricValue(technicalDetails.ambiguousWordShare, "share") ?? "Not available" },
              { term: "Collision-flagged word share", description: formatMetricValue(technicalDetails.collisionFlaggedWordShare, "share") ?? "Not available" },
              { term: "Unmatched word share", description: formatMetricValue(technicalDetails.unmatchedWordShare, "share") ?? "Not available" },
              { term: "Structured-content exclusion share", description: formatMetricValue(technicalDetails.structuredContentExclusionShare, "share") ?? "Not available" },
              { term: "Report-side primary eligible", description: technicalDetails.reportSidePrimaryEligible === null ? "Not available" : technicalDetails.reportSidePrimaryEligible ? "Yes" : "No" },
              { term: "Alignment-change primary eligible", description: technicalDetails.alignmentChangePrimaryEligible === null ? "Not available" : technicalDetails.alignmentChangePrimaryEligible ? "Yes" : "No" },
              { term: "Disclosure-change primary eligible", description: technicalDetails.disclosureChangePrimaryEligible === null ? "Not available" : technicalDetails.disclosureChangePrimaryEligible ? "Yes" : "No" },
              { term: "Report-side warning", description: technicalDetails.reportSideWarning ?? "None" },
              { term: "Alignment-change warning", description: technicalDetails.alignmentChangeWarning ?? "None" },
              { term: "Disclosure-change warning", description: technicalDetails.disclosureChangeWarning ?? "None" },
              { term: "Aligned passages", description: formatCount(passageComposition.totalCount) },
            ]}
          />
        </TechnicalDetails>
      </section>
    </>
  );
}
