import type { DiscoveryType, RankScope } from "@/lib/config/discovery";
import type { DiscoveryItem } from "@/lib/domain/discovery";

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
}
