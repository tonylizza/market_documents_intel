"use client";

import { useRef } from "react";
import { DISCOVERY_TYPE_CONFIG, RANK_SCOPES, type DiscoveryType, type RankScope } from "@/lib/config/discovery";
import type { RawQuality } from "@/lib/domain/quality";
import { resolveQualityLabel } from "@/lib/formatting/labels";
import type { DiscoveryFilterOptions, DiscoveryFilterState } from "@/lib/domain/discovery";
import styles from "./DiscoveryFilters.module.css";

export interface DiscoveryFiltersProps {
  availableTypes: readonly DiscoveryType[];
  filters: DiscoveryFilterState;
  filterOptions: DiscoveryFilterOptions;
}

const SCOPE_LABELS: Record<RankScope, string> = {
  corpus: "Whole corpus",
  company_history: "This company's history",
  latest_comparisons: "Latest comparisons only",
};

const QUALITY_TIERS: readonly RawQuality[] = ["GOOD", "USABLE", "NEEDS_REVIEW", "FAILED"];

/**
 * A real `<form method="get">` (works without JavaScript; auto-submits on
 * change as an enhancement) -- every filter becomes a `/discover?...` query
 * parameter, so filtered views are shareable. The minimum-quality select is
 * built from the *selected type's own* quality dimension vocabulary
 * (`DISCOVERY_TYPE_CONFIG[type].qualityDimension`) -- never a combined
 * cross-dimension quality scale.
 */
export function DiscoveryFilters({ availableTypes, filters, filterOptions }: DiscoveryFiltersProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const typeConfig = DISCOVERY_TYPE_CONFIG[filters.type];

  function submitOnChange() {
    formRef.current?.requestSubmit();
  }

  return (
    <form ref={formRef} method="get" action="/discover" className={styles.form} aria-label="Discovery filters">
      <div className={styles.field}>
        <label htmlFor="discovery-type">Ranking</label>
        <select id="discovery-type" name="type" defaultValue={filters.type} onChange={submitOnChange}>
          {availableTypes.map((type) => (
            <option key={type} value={type}>
              {DISCOVERY_TYPE_CONFIG[type].title}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label htmlFor="discovery-scope">Scope</label>
        <select id="discovery-scope" name="scope" defaultValue={filters.scope} onChange={submitOnChange}>
          {RANK_SCOPES.map((scope) => (
            <option key={scope} value={scope}>
              {SCOPE_LABELS[scope]}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label htmlFor="discovery-company">Company</label>
        <select id="discovery-company" name="company" defaultValue={filters.company ?? ""} onChange={submitOnChange}>
          <option value="">All companies</option>
          {filterOptions.companies.map((company) => (
            <option key={company.ticker} value={company.ticker}>
              {company.name} ({company.ticker})
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label htmlFor="discovery-min-quality">Minimum {typeConfig.qualityDimension.replace("-", " ")} quality</label>
        <select id="discovery-min-quality" name="minQuality" defaultValue={filters.minQuality ?? ""} onChange={submitOnChange}>
          <option value="">No minimum</option>
          {QUALITY_TIERS.map((tier) => (
            <option key={tier} value={tier}>
              {resolveQualityLabel(typeConfig.qualityDimension, tier, null)}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label htmlFor="discovery-period-start">From</label>
        <input
          id="discovery-period-start"
          type="date"
          name="periodStart"
          defaultValue={filters.periodStart ?? ""}
          min={filterOptions.earliestPeriodEnd ?? undefined}
          max={filterOptions.latestPeriodEnd ?? undefined}
          onChange={submitOnChange}
        />
      </div>
      <div className={styles.field}>
        <label htmlFor="discovery-period-end">To</label>
        <input
          id="discovery-period-end"
          type="date"
          name="periodEnd"
          defaultValue={filters.periodEnd ?? ""}
          min={filterOptions.earliestPeriodEnd ?? undefined}
          max={filterOptions.latestPeriodEnd ?? undefined}
          onChange={submitOnChange}
        />
      </div>

      <button type="submit" className={styles.submit}>
        Apply filters
      </button>
    </form>
  );
}
