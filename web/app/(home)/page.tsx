import Link from "next/link";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import { getCompaniesPageViewModel } from "@/lib/services/company-service";
import { PageHeader } from "@/components/PageHeader";
import { SectionHeader } from "@/components/SectionHeader";
import { DataCoverageSummary } from "@/components/DataCoverageSummary";
import { CompanyCard } from "@/components/CompanyCard";
import { MetricCard } from "@/components/MetricCard";
import { EmptyState } from "@/components/EmptyState";
import { formatMetricValue } from "@/lib/formatting/numbers";
import { PRODUCT_DESCRIPTION, PRODUCT_NAME, PRODUCT_SUBTITLE } from "@/lib/config/product";
import styles from "./page.module.css";

export default async function CompaniesHomePage() {
  const repository = new PostgresCompanyRepository();

  // Deliberately not caught here -- letting DB failures propagate lets
  // error.tsx render the friendly fallback instead of duplicating that
  // logic inline.
  const viewModel = await getCompaniesPageViewModel(repository);

  return (
    <>
      <PageHeader title={PRODUCT_NAME} subtitle={PRODUCT_SUBTITLE} description={PRODUCT_DESCRIPTION} />

      <section aria-label="Corpus summary" className={styles.section}>
        <DataCoverageSummary summary={viewModel.summary} />
      </section>

      <section aria-labelledby="companies-heading" className={styles.section}>
        <SectionHeader
          id="companies-heading"
          title="Companies"
          description="Select a company to see report coverage and its most recent disclosure comparison."
        />
        {viewModel.companies.length === 0 ? (
          <EmptyState
            title="No companies are published yet"
            description="Check back once the first publication has been activated."
          />
        ) : (
          <div className={styles.grid}>
            {viewModel.companies.map((company) => (
              <CompanyCard company={company} key={company.companyId} />
            ))}
          </div>
        )}
      </section>

      {viewModel.latestSignalSections.length > 0 && (
        <section aria-labelledby="latest-signals-heading" className={styles.section}>
          <SectionHeader
            id="latest-signals-heading"
            title="Latest signals"
            description="The largest currently primary-eligible language-based changes across each company's most recent comparison."
          />
          <div className={styles.signalSections}>
            {viewModel.latestSignalSections.map((section) => (
              <div key={section.discoveryType}>
                <h3 className={styles.signalSectionTitle}>{section.title}</h3>
                <div className={styles.grid}>
                  {section.items.map((item) => (
                    <MetricCard
                      key={item.id}
                      title={item.companyName}
                      subtitle={item.companyTicker}
                      value={formatMetricValue(item.supportingValue, item.supportingUnit) ?? String(item.supportingValue)}
                      qualityLabel={item.qualityLabel}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className={styles.methodologyCallout}>
        <p>
          Curious how these figures are calculated?{" "}
          <Link href="/methodology">Read the methodology →</Link>
        </p>
      </section>
    </>
  );
}
