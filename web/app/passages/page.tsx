import type { Metadata } from "next";
import { PostgresPassageRepository } from "@/lib/repositories/postgres-passage-repository";
import { buildPassageSearchViewModel } from "@/lib/services/passage-search-service";
import { parsePassageSearchParams, hasSearchableInput, type RawSearchParamsInput } from "@/lib/services/passage-search-params";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { PassageSearchFilters } from "@/components/PassageSearchFilters";
import { PassageResultsList } from "@/components/PassageResultsList";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Passages" };

/** Highly parameterized full-text search -- always dynamically rendered
 * (no `revalidate`), never cached across the effectively unbounded space of
 * query/filter combinations (see docs/frontend.md's caching section). */
export const dynamic = "force-dynamic";

interface PassagesPageProps {
  searchParams: Promise<RawSearchParamsInput>;
}

export default async function PassagesPage({ searchParams }: PassagesPageProps) {
  const raw = await searchParams;
  const params = parsePassageSearchParams(raw);
  const repository = new PostgresPassageRepository();

  let viewModel: Awaited<ReturnType<typeof buildPassageSearchViewModel>> | null = null;
  let failed = false;
  try {
    viewModel = await buildPassageSearchViewModel(repository, params);
  } catch (error) {
    failed = true;
    console.error("Failed to load passage search results:", (error as Error).message);
  }

  if (failed || !viewModel) {
    return (
      <>
        <PageHeader title="Passages" subtitle="Corpus-wide passage search" />
        <ErrorState title="Passage search is temporarily unavailable" />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Passages"
        subtitle="Corpus-wide passage search"
        description="Keyword search across every published passage, backed by PostgreSQL full-text search -- not a semantic or AI-generated result. Headings are weighted above body text; results connect back to full report-comparison evidence."
      />

      <section aria-label="Passage search filters" className={styles.section}>
        <PassageSearchFilters params={params} filterOptions={viewModel.filterOptions} />
      </section>

      <section aria-labelledby="passage-results-heading" className={styles.section}>
        <h2 id="passage-results-heading" className="visually-hidden">
          Search results
        </h2>
        {!hasSearchableInput(params) ? (
          <EmptyState
            title="Enter a search term or choose a filter to begin"
            description="Passage search never loads the full corpus at once -- add a keyword (e.g. liquidity, going concern, governance) or select a structured filter such as company or alignment status."
          />
        ) : (
          <PassageResultsList page={viewModel.page} />
        )}
      </section>
    </>
  );
}
