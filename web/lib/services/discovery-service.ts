import type { CompanyRepository } from "@/lib/repositories/company-repository";
import type { DiscoveryRepository } from "@/lib/repositories/discovery-repository";
import type { DiscoveryFilterOptions, DiscoveryFilterState, DiscoveryItem } from "@/lib/domain/discovery";
import {
  DISCOVERY_TYPE_CONFIG,
  isDiscoveryType,
  resolveRankScope,
  type DiscoveryType,
  type DiscoveryTypeConfig,
  type RankScope,
} from "@/lib/config/discovery";
import { isRawQuality, meetsMinimumQuality, type RawQuality } from "@/lib/domain/quality";
import { rawQualityFromLabel } from "@/lib/formatting/labels";

export interface DiscoveryPageParams {
  type?: string | null;
  scope?: string | null;
  company?: string | null;
  minQuality?: string | null;
  periodStart?: string | null;
  periodEnd?: string | null;
}

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** Validates a raw query-string date -- never passed unvalidated into a SQL
 * parameter. `null` for anything that isn't a plain `YYYY-MM-DD`. */
export function resolvePeriodDateParam(value: string | null | undefined): string | null {
  return value && ISO_DATE_PATTERN.test(value) ? value : null;
}

export interface DiscoveryPageViewModel {
  availableTypes: DiscoveryType[];
  selectedType: DiscoveryType;
  typeConfig: DiscoveryTypeConfig;
  scope: RankScope;
  filters: DiscoveryFilterState;
  filterOptions: DiscoveryFilterOptions;
  items: DiscoveryItem[];
}

/** Falls back to the first available (non-empty) discovery type when the
 * requested one is invalid or currently has zero items -- never renders an
 * empty ranking tab, never trusts the raw query-string value directly. */
export function resolveSelectedDiscoveryType(
  typeParam: string | null | undefined,
  availableTypes: readonly DiscoveryType[],
): DiscoveryType | null {
  if (typeParam && isDiscoveryType(typeParam) && availableTypes.includes(typeParam)) {
    return typeParam;
  }
  return availableTypes[0] ?? null;
}

export function resolveMinQualityParam(value: string | null | undefined): RawQuality | null {
  return isRawQuality(value) ? value : null;
}

/**
 * Type-specific quality filter: resolves each item's raw quality tier from
 * its `qualityLabel` text using the ranking's own quality dimension (never
 * a generic cross-dimension comparison), then keeps only items at or above
 * `minQuality`. An item whose label can't be resolved against the expected
 * dimension's vocabulary is excluded rather than assumed to pass.
 */
export function filterDiscoveryItemsByMinQuality(
  items: readonly DiscoveryItem[],
  qualityDimension: DiscoveryTypeConfig["qualityDimension"],
  minQuality: RawQuality | null,
): DiscoveryItem[] {
  if (!minQuality) return [...items];
  return items.filter((item) => {
    const raw = rawQualityFromLabel(qualityDimension, item.qualityLabel);
    return meetsMinimumQuality(raw, minQuality);
  });
}

/**
 * Two purposeful queries beyond `listAvailableDiscoveryTypes` (one for
 * items, plus company/period filter options reused from `CompanyRepository`
 * -- never a duplicate query for data already fetched elsewhere). Rank
 * order is never recomputed here: `items` preserves the repository's
 * `ORDER BY rank` order exactly, quality filtering only removes rows.
 */
export async function getDiscoveryPageViewModel(
  discoveryRepository: DiscoveryRepository,
  companyRepository: CompanyRepository,
  params: DiscoveryPageParams,
): Promise<DiscoveryPageViewModel> {
  const availableTypes = await discoveryRepository.listAvailableDiscoveryTypes();
  const selectedType = resolveSelectedDiscoveryType(params.type, availableTypes);
  const scope = resolveRankScope(params.scope);
  const minQuality = resolveMinQualityParam(params.minQuality);
  const companyTicker = params.company ?? null;
  const periodStart = resolvePeriodDateParam(params.periodStart);
  const periodEnd = resolvePeriodDateParam(params.periodEnd);

  const [rawItems, companies, summary] = await Promise.all([
    selectedType
      ? discoveryRepository.getDiscoveryItems({ type: selectedType, scope, companyTicker, periodStart, periodEnd })
      : Promise.resolve([]),
    companyRepository.listCompanies(),
    companyRepository.getApplicationDataSummary(),
  ]);

  const typeConfig = selectedType ? DISCOVERY_TYPE_CONFIG[selectedType] : DISCOVERY_TYPE_CONFIG.largest_uncertainty_increase;
  const items = filterDiscoveryItemsByMinQuality(rawItems, typeConfig.qualityDimension, minQuality);

  return {
    availableTypes,
    selectedType: selectedType ?? typeConfig.type,
    typeConfig,
    scope,
    filters: { type: selectedType ?? typeConfig.type, scope, company: companyTicker, minQuality, periodStart, periodEnd },
    filterOptions: {
      companies: companies.map((c) => ({ ticker: c.ticker, name: c.name })),
      earliestPeriodEnd: summary.earliestPeriodEnd,
      latestPeriodEnd: summary.latestPeriodEnd,
    },
    items,
  };
}
