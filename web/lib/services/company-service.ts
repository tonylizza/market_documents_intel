import type { CompanyRepository } from "@/lib/repositories/company-repository";
import { LANGUAGE_DISCOVERY_TYPES } from "@/lib/repositories/postgres-company-repository";
import type { CompanyCardSummary, DiscoveryItemSummary } from "@/lib/domain/comparison";
import type { ApplicationDataSummary } from "@/lib/domain/metric";

export interface LatestSignalSection {
  discoveryType: string;
  title: string;
  items: DiscoveryItemSummary[];
}

export interface CompaniesPageViewModel {
  summary: ApplicationDataSummary;
  companies: CompanyCardSummary[];
  latestSignalSections: LatestSignalSection[];
}

const SECTION_TITLES: Record<string, string> = {
  largest_uncertainty_increase: "Latest uncertainty increases",
  largest_negative_tone_shift: "Latest tone deterioration",
  largest_risk_introduction: "Latest risk-language introduction",
  largest_risk_removal: "Latest risk-language removal",
  largest_governance_shift: "Latest governance changes",
  largest_financial_condition_shift: "Latest financial-condition changes",
};

/**
 * Groups discovery items by type into named sections, keeping only
 * sections that actually have qualifying data -- never renders an empty
 * "Largest overall change" (or any other) ranking. A section with no
 * eligible items in this publication is omitted entirely, not shown with
 * a placeholder.
 */
export function buildLatestSignalSections(items: readonly DiscoveryItemSummary[]): LatestSignalSection[] {
  const grouped = new Map<string, DiscoveryItemSummary[]>();
  for (const item of items) {
    const list = grouped.get(item.discoveryType);
    if (list) {
      list.push(item);
    } else {
      grouped.set(item.discoveryType, [item]);
    }
  }

  return LANGUAGE_DISCOVERY_TYPES.map((type) => ({
    discoveryType: type,
    title: SECTION_TITLES[type] ?? type,
    items: grouped.get(type) ?? [],
  })).filter((section) => section.items.length > 0);
}

export async function getCompaniesPageViewModel(repository: CompanyRepository): Promise<CompaniesPageViewModel> {
  const [summary, companies, discoveryItems] = await Promise.all([
    repository.getApplicationDataSummary(),
    repository.getCompanyCardSummaries(),
    repository.getLatestComparisonSummaries(),
  ]);

  return {
    summary,
    companies,
    latestSignalSections: buildLatestSignalSections(discoveryItems),
  };
}
