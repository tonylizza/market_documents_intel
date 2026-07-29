import type { Company, CompanyDetail, CompanyHistory } from "@/lib/domain/company";
import type { CompanyCardSummary, DiscoveryItemSummary } from "@/lib/domain/comparison";
import type { ApplicationDataSummary } from "@/lib/domain/metric";

/**
 * No generic/arbitrary-query method exists on this interface by design --
 * every method here is a named, purpose-built read for one page's needs.
 */
export interface CompanyRepository {
  listCompanies(): Promise<Company[]>;
  getCompanyCardSummaries(): Promise<CompanyCardSummary[]>;
  /** Language-based discovery items at `rank_scope='latest_comparisons'`,
   * restricted to the caller-supplied discovery types (defaults to every
   * currently primary-eligible language-based type -- never the two
   * feature-quality-gated types, which are absent from the underlying data
   * while review-qualified). */
  getLatestComparisonSummaries(discoveryTypes?: readonly string[]): Promise<DiscoveryItemSummary[]>;
  getApplicationDataSummary(): Promise<ApplicationDataSummary>;
  /** Case-insensitive ticker lookup -- `null` for an unknown ticker (the
   * page renders a 404, never a synthesized empty company). */
  getCompanyByTicker(ticker: string): Promise<CompanyDetail | null>;
  /** One query for the company header + one for its complete, chronologically
   * ordered comparison history -- never one query per comparison card. */
  getCompanyHistory(ticker: string): Promise<CompanyHistory | null>;
}
