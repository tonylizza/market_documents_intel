import type { Metadata } from "next";
import { PostgresPassageRepository } from "@/lib/repositories/postgres-passage-repository";
import { PostgresSemanticRetrievalRepository } from "@/lib/repositories/postgres-semantic-retrieval-repository";
import { buildPassageSearchViewModel } from "@/lib/services/passage-search-service";
import { parsePassageSearchParams, hasSearchableInput, type RawSearchParamsInput } from "@/lib/services/passage-search-params";
import { parseRetrievalMode } from "@/lib/services/retrieval-search-params";
import { searchHybrid, searchSemantic } from "@/lib/services/retrieval-service";
import { CachingQueryEmbeddingProvider, HttpQueryEmbeddingProvider, queryEmbeddingCacheKeyPrefix, loadHttpQueryEmbeddingProviderConfig } from "@/lib/services/query-embedding-provider";
import { getRetrievalConfig } from "@/lib/config/retrieval-config";
import type { RetrievalPage } from "@/lib/domain/retrieval";
import { PageHeader } from "@/components/PageHeader";
import { ErrorState } from "@/components/ErrorState";
import { EmptyState } from "@/components/EmptyState";
import { PassageSearchFilters } from "@/components/PassageSearchFilters";
import { PassageResultsList } from "@/components/PassageResultsList";
import { RetrievalResultsList } from "@/components/RetrievalResultsList";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Passages" };

/** Highly parameterized full-text/semantic/hybrid search -- always
 * dynamically rendered (no `revalidate`), never cached across the
 * effectively unbounded space of query/filter/mode combinations (see
 * docs/frontend.md's caching section). */
export const dynamic = "force-dynamic";

interface PassagesPageProps {
  searchParams: Promise<RawSearchParamsInput>;
}

const MODE_DESCRIPTIONS = {
  keyword: "Keyword search across every published passage, backed by PostgreSQL full-text search -- not a semantic or AI-generated result.",
  semantic: "Meaning-based search: finds passages with similar meaning even when the wording differs. Similarity is a relative ranking signal, not a probability or confidence score.",
  hybrid: "Combines keyword and meaning-based retrieval using reciprocal rank fusion.",
} as const;

async function buildRetrievalPage(mode: "semantic" | "hybrid", params: ReturnType<typeof parsePassageSearchParams>, maxResults: number): Promise<RetrievalPage> {
  const semanticRepository = new PostgresSemanticRetrievalRepository();
  const providerConfig = loadHttpQueryEmbeddingProviderConfig();
  const embeddingProvider = new CachingQueryEmbeddingProvider(
    new HttpQueryEmbeddingProvider(providerConfig),
    queryEmbeddingCacheKeyPrefix(providerConfig),
  );
  return mode === "semantic"
    ? searchSemantic(semanticRepository, embeddingProvider, params, maxResults)
    : searchHybrid(semanticRepository, embeddingProvider, params, maxResults);
}

export default async function PassagesPage({ searchParams }: PassagesPageProps) {
  const raw = await searchParams;
  const params = parsePassageSearchParams(raw);
  const retrievalConfig = getRetrievalConfig();
  const mode = parseRetrievalMode(raw, retrievalConfig.defaultSearchMode);
  const repository = new PostgresPassageRepository();

  if (mode === "keyword") {
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
        <PageHeader title="Passages" subtitle="Corpus-wide passage search" description={MODE_DESCRIPTIONS.keyword} />
        <section aria-label="Passage search filters" className={styles.section}>
          <PassageSearchFilters params={params} filterOptions={viewModel.filterOptions} mode={mode} />
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

  // Semantic/hybrid modes still need filter options for the sidebar (same
  // corpus vocabulary, same repository) even though results come from the
  // new retrieval service.
  let filterOptions: Awaited<ReturnType<typeof repository.getPassageFilterOptions>> | null = null;
  let retrievalPage: RetrievalPage | null = null;
  let failed = false;
  try {
    [filterOptions, retrievalPage] = await Promise.all([
      repository.getPassageFilterOptions(),
      params.query ? buildRetrievalPage(mode, params, 20) : Promise.resolve({ results: [], mode, weakMatchNotice: false, providerUnavailable: false } as RetrievalPage),
    ]);
  } catch (error) {
    failed = true;
    console.error(`Failed to load ${mode} passage search results:`, (error as Error).message);
  }

  if (failed || !filterOptions || !retrievalPage) {
    return (
      <>
        <PageHeader title="Passages" subtitle="Corpus-wide passage search" />
        <ErrorState title="Passage search is temporarily unavailable" />
      </>
    );
  }

  return (
    <>
      <PageHeader title="Passages" subtitle="Corpus-wide passage search" description={MODE_DESCRIPTIONS[mode]} />
      <section aria-label="Passage search filters" className={styles.section}>
        <PassageSearchFilters params={params} filterOptions={filterOptions} mode={mode} />
      </section>
      <section aria-labelledby="passage-results-heading" className={styles.section}>
        <h2 id="passage-results-heading" className="visually-hidden">
          Search results
        </h2>
        {!params.query ? (
          <EmptyState
            title="Enter a search term to begin"
            description={`${mode === "semantic" ? "Semantic" : "Hybrid"} search requires a search term -- structured filters alone aren't enough to rank results by meaning.`}
          />
        ) : (
          <RetrievalResultsList page={retrievalPage} />
        )}
      </section>
    </>
  );
}
