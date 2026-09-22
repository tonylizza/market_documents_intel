import type { DiscoveryType, RankScope } from "@/lib/config/discovery";
import type { RawQuality } from "@/lib/domain/quality";

/** One ranked item on `/discover` -- richer than `DiscoveryItemSummary`
 * (used only for the home page's "latest signals" strip): carries the
 * comparison's period dates and a resolved finding headline so the results
 * table/cards need no further per-row query. */
export interface DiscoveryItem {
  id: string;
  discoveryType: DiscoveryType;
  rankScope: RankScope;
  rank: number;
  percentile: number | null;
  companyId: string;
  companyTicker: string;
  companyName: string;
  reportComparisonId: string;
  earlierPeriodEnd: string | null;
  laterPeriodEnd: string | null;
  findingHeadline: string;
  supportingValue: number;
  supportingValueDisplay: string | null;
  supportingUnit: string;
  qualityLabel: string;
}

/** Shareable, validated `/discover` filter state -- every field is bounded/
 * validated against a known allowlist before use (see
 * `lib/schemas/discovery.ts`), never trusted raw from the query string. */
export interface DiscoveryFilterState {
  type: DiscoveryType;
  scope: RankScope;
  company: string | null;
  minQuality: RawQuality | null;
  periodStart: string | null;
  periodEnd: string | null;
}

export interface DiscoveryFilterOptions {
  companies: { ticker: string; name: string }[];
  earliestPeriodEnd: string | null;
  latestPeriodEnd: string | null;
}

/**
 * Track 7F.4 item 8 -- for a company filtered to `largest_financial_
 * condition_shift` with zero eligible Discover items, distinguishes *why*:
 * no comparisons published at all, comparisons exist but none clear the
 * report-side quality gate, or quality-eligible comparisons exist but none
 * clear the 0.04 materiality bar (in which case the largest observed
 * quality-eligible pair is still shown, clearly labeled -- never ranked as
 * an eligible finding). Never collapsed into one generic empty state.
 */
export type FinancialConditionCompanyStatus =
  | { status: "no_comparisons" }
  | { status: "failed_quality" }
  | {
      status: "below_materiality";
      observedValue: number;
      threshold: number;
      reportComparisonId: string;
      earlierPeriodEnd: string | null;
      laterPeriodEnd: string | null;
    };
