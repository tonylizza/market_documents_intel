import type { Metadata } from "next";
import Link from "next/link";
import { PostgresCompanyRepository } from "@/lib/repositories/postgres-company-repository";
import { PostgresDiscoveryRepository } from "@/lib/repositories/postgres-discovery-repository";
import { getDiscoveryPageViewModel } from "@/lib/services/discovery-service";
import { PageHeader } from "@/components/PageHeader";
import { SectionHeader } from "@/components/SectionHeader";
import { EmptyState } from "@/components/EmptyState";
import { DiscoveryFilters } from "@/components/DiscoveryFilters";
import { DiscoveryResultsTable } from "@/components/DiscoveryResultsTable";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Discover" };

interface DiscoverPageProps {
  searchParams: Promise<{
    type?: string;
    scope?: string;
    company?: string;
    minQuality?: string;
    periodStart?: string;
    periodEnd?: string;
  }>;
}

/**
 * Corpus-wide discovery rankings (Milestone 7A.3). Available ranking
 * categories are the published types that have current discovery items.
 * Track 7F.9: rankings whose methodology is under review are listed
 * explicitly as "not currently published" -- never shown as an empty
 * ranking, which would wrongly suggest that no change occurred.
 */
export default async function DiscoverPage({ searchParams }: DiscoverPageProps) {
  const params = await searchParams;
  const companyRepository = new PostgresCompanyRepository();
  const discoveryRepository = new PostgresDiscoveryRepository();

  // Deliberately not caught here -- letting DB failures propagate lets
  // error.tsx render the friendly fallback instead of duplicating that
  // logic inline.
  const viewModel = await getDiscoveryPageViewModel(discoveryRepository, companyRepository, params);

  return (
    <>
      <PageHeader
        title="Discover"
        subtitle="Corpus-wide, category-specific rankings"
        description="Each ranking below is category-specific -- there is no single opaque combined score. Rankings describe changes in report language measured with word dictionaries, not changes in the business itself. Ties use deterministic ordering."
      />

      {viewModel.requestedUnderReviewType ? (
        <section aria-labelledby="under-review-heading" className={styles.section}>
          <SectionHeader id="under-review-heading" title={viewModel.requestedUnderReviewType.title} />
          <EmptyState
            title="Not currently published: methodology under review"
            description={`${viewModel.requestedUnderReviewType.underReviewReason ?? ""} This does not mean that no change occurred.`}
          >
            <Link href="/discover">Back to published rankings →</Link>
          </EmptyState>
        </section>
      ) : viewModel.availableTypes.length === 0 ? (
        <EmptyState
          title="No discovery rankings are currently available"
          description="Check back once the active publication includes eligible, quality-gated discovery items."
        />
      ) : (
        <>
          <section aria-label="Discovery filters" className={styles.section}>
            <DiscoveryFilters availableTypes={viewModel.availableTypes} filters={viewModel.filters} filterOptions={viewModel.filterOptions} />
          </section>

          <section aria-labelledby="results-heading" className={styles.section}>
            <SectionHeader id="results-heading" title={viewModel.typeConfig.title} description={viewModel.typeConfig.description} />
            <div className={styles.tableScroll}>
              <DiscoveryResultsTable
                items={viewModel.items}
                financialConditionCompanyStatus={viewModel.financialConditionCompanyStatus}
                governanceCompanyStatus={viewModel.governanceCompanyStatus}
              />
            </div>
          </section>
        </>
      )}

      {viewModel.underReviewTypes.length > 0 && (
        <section aria-labelledby="not-published-heading" className={styles.section}>
          <SectionHeader
            id="not-published-heading"
            title="Not currently published"
            description="These rankings are under methodology review. Their absence does not mean that no change occurred."
          />
          <ul>
            {viewModel.underReviewTypes.map((config) => (
              <li key={config.type}>
                <Link href={`/discover?type=${config.type}`}>{config.title}</Link> -- {config.underReviewReason}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
