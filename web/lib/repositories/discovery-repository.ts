import type { DiscoveryType, RankScope } from "@/lib/config/discovery";
import type { DiscoveryItem, FinancialConditionCompanyStatus, GovernanceCompanyStatus } from "@/lib/domain/discovery";

export interface DiscoveryItemFilters {
  type: DiscoveryType;
  scope: RankScope;
  /** Ticker, exact match (case-insensitive) -- `null`/omitted means all
   * companies. */
  companyTicker?: string | null;
  /** Inclusive `later_period_end` bounds -- `null`/omitted means
   * unbounded. */
  periodStart?: string | null;
  periodEnd?: string | null;
}

export interface DiscoveryRepository {
  /** Discovery types with at least one row in the current publication --
   * derived from actual data, never a hardcoded "always show all 8"
   * assumption. */
  listAvailableDiscoveryTypes(): Promise<DiscoveryType[]>;
  getDiscoveryItems(filters: DiscoveryItemFilters): Promise<DiscoveryItem[]>;
  /** Track 7F.4 item 8 -- only meaningful for `largest_financial_condition_
   * shift`, called when a company-filtered query returns zero eligible
   * items, to distinguish no-comparisons / failed-quality / below-
   * materiality (never a collapsed generic empty state). */
  getFinancialConditionCompanyStatus(companyTicker: string): Promise<FinancialConditionCompanyStatus>;
  /** Track 7F.7a.1 -- exact mirror of `getFinancialConditionCompanyStatus`
   * above, for `largest_governance_shift` (M3-G, threshold 0.05). */
  getGovernanceCompanyStatus(companyTicker: string): Promise<GovernanceCompanyStatus>;
}
