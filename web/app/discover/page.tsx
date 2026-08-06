import type { Metadata } from "next";
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
 * categories are derived from actual current discovery items (never a
 * hardcoded "always show 8 tabs" list), so `largest_overall_change`/
 * `largest_new_disclosure_share` stay absent while review-qualified.
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
        description="Each ranking below is category-specific -- there is no single opaque combined score. Ties use deterministic ordering. Review-qualified disclosure-change scores are excluded from these rankings until independently confirmed."
      />

      {viewModel.availableTypes.length === 0 ? (
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
              <DiscoveryResultsTable items={viewModel.items} />
            </div>
          </section>
        </>
      )}
    </>
  );
}
