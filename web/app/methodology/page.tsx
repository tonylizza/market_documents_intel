import type { Metadata } from "next";
import { PostgresMethodologyRepository } from "@/lib/repositories/postgres-methodology-repository";
import { getMethodologyPageViewModel } from "@/lib/services/methodology-service";
import { PageHeader } from "@/components/PageHeader";
import { MethodologySection } from "@/components/MethodologySection";
import { StatusLegend } from "@/components/StatusLegend";
import { DefinitionList } from "@/components/DefinitionList";
import { ErrorState } from "@/components/ErrorState";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Methodology",
  description: "How disclosure comparisons, quality labels, and discovery rankings are computed.",
};

export default async function MethodologyPage() {
  const repository = new PostgresMethodologyRepository();

  let viewModel: Awaited<ReturnType<typeof getMethodologyPageViewModel>> | null = null;
  let failed = false;

  try {
    viewModel = await getMethodologyPageViewModel(repository);
  } catch (error) {
    failed = true;
    console.error("Failed to load Methodology page data:", (error as Error).message);
  }

  return (
    <>
      <PageHeader
        title="Methodology"
        subtitle="How this analysis works"
        description="A plain-language walkthrough of how disclosures are compared, scored, and labeled -- with technical detail available where useful."
      />

      {failed || !viewModel ? (
        <ErrorState title="Methodology content is temporarily unavailable" />
      ) : (
        <>
          <div className={styles.sections}>
            {viewModel.sections.map((section) => (
              <MethodologySection section={section} key={section.id} />
            ))}
          </div>

          <section aria-labelledby="quality-vocab-heading" className={styles.section}>
            <h2 id="quality-vocab-heading" className={styles.heading}>
              Quality label vocabularies at a glance
            </h2>
            <p className={styles.sectionIntro}>
              Each dimension uses its own four-tier vocabulary -- the same tier name never means the same thing
              across dimensions.
            </p>
            <div className={styles.legends}>
              <StatusLegend dimension="report-side" />
              <StatusLegend dimension="alignment-change" />
              <StatusLegend dimension="disclosure-change" />
            </div>
          </section>

          {viewModel.metrics.length > 0 && (
            <section aria-labelledby="metric-catalog-heading" className={styles.section}>
              <h2 id="metric-catalog-heading" className={styles.heading}>
                Metric catalog
              </h2>
              <DefinitionList
                items={viewModel.metrics.map((metric) => ({
                  term: metric.displayName,
                  description: `${metric.shortDescription} (unit: ${metric.unit})`,
                }))}
              />
            </section>
          )}

          <section className={styles.adviceNotice} aria-label="Non-investment-advice notice">
            <p>{viewModel.nonInvestmentAdviceStatement}</p>
          </section>
        </>
      )}
    </>
  );
}
