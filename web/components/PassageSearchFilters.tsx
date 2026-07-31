"use client";

import { useRef } from "react";
import Link from "next/link";
import type { PassageFilterOptions, PassageSearchParams, PassageSortKey } from "@/lib/domain/passage";
import { PASSAGE_SORT_KEYS } from "@/lib/domain/passage";
import type { RetrievalMode } from "@/lib/domain/retrieval";
import { PASSAGE_SORT_LABELS } from "@/lib/config/passage-vocabulary";
import { SearchModeSelector } from "@/components/SearchModeSelector";
import styles from "./PassageSearchFilters.module.css";

export interface PassageSearchFiltersProps {
  params: PassageSearchParams;
  filterOptions: PassageFilterOptions;
  mode: RetrievalMode;
}

const TRISTATE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Any" },
  { value: "1", label: "Yes" },
  { value: "0", label: "No" },
];

function triState(value: boolean | null): string {
  return value === null ? "" : value ? "1" : "0";
}

/**
 * The single `/passages` search + filter form -- a real `<form
 * method="get">` (works without JavaScript; auto-submits on select/checkbox
 * change as a progressive enhancement, matching `DiscoveryFilters`'s
 * pattern). Every field name is a controlled, documented URL parameter
 * (`parsePassageSearchParams` is the single source of truth for the
 * allowed set) -- there is no free-text sort/order-by field anywhere here.
 */
export function PassageSearchFilters({ params, filterOptions, mode }: PassageSearchFiltersProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const subcategoryOptions = params.category ? (filterOptions.subcategoriesByCategory[params.category] ?? []) : [];

  function submitOnChange() {
    formRef.current?.requestSubmit();
  }

  return (
    <form ref={formRef} method="get" action="/passages" role="search" aria-label="Passage search" className={styles.form}>
      <SearchModeSelector mode={mode} onChange={submitOnChange} />
      <div className={styles.queryRow}>
        <label htmlFor="passage-query" className={styles.queryLabel}>
          Search passage text
        </label>
        <input
          id="passage-query"
          type="search"
          name="q"
          defaultValue={params.query ?? ""}
          placeholder="e.g. liquidity, going concern, governance"
          maxLength={200}
          className={styles.queryInput}
        />
        <label className={styles.checkboxLabel}>
          <input type="checkbox" name="phrase" value="1" defaultChecked={params.exactPhrase} />
          Exact phrase
        </label>
        <button type="submit" className={styles.submit}>
          Search
        </button>
        <Link href="/passages" className={styles.reset}>
          Reset
        </Link>
      </div>

      <div className={styles.filterGrid}>
        <div className={styles.field}>
          <label htmlFor="passage-company">Company</label>
          <select id="passage-company" name="company" defaultValue={params.company ?? ""} onChange={submitOnChange}>
            <option value="">All companies</option>
            {filterOptions.companies.map((company) => (
              <option key={company.value} value={company.value}>
                {company.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-period-start">Report period from</label>
          <input id="passage-period-start" type="date" name="periodStart" defaultValue={params.periodStart ?? ""} onChange={submitOnChange} />
        </div>
        <div className={styles.field}>
          <label htmlFor="passage-period-end">Report period to</label>
          <input id="passage-period-end" type="date" name="periodEnd" defaultValue={params.periodEnd ?? ""} onChange={submitOnChange} />
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-side">Report side</label>
          <select id="passage-side" name="side" defaultValue={params.reportSide ?? ""} onChange={submitOnChange}>
            <option value="">Any</option>
            <option value="EARLIER">Earlier report</option>
            <option value="LATER">Later report</option>
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-status">Alignment status</label>
          <select id="passage-status" name="status" defaultValue={params.alignmentStatus ?? ""} onChange={submitOnChange}>
            <option value="">Any</option>
            {filterOptions.alignmentStatuses.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-confidence">Confidence</label>
          <select id="passage-confidence" name="confidence" defaultValue={params.confidence ?? ""} onChange={submitOnChange}>
            <option value="">Any</option>
            {filterOptions.confidenceLevels.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-type">Passage type</label>
          <select id="passage-type" name="type" defaultValue={params.passageType ?? ""} onChange={submitOnChange}>
            <option value="">Any</option>
            {filterOptions.passageTypes.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-category">Financial-language category</label>
          <select id="passage-category" name="category" defaultValue={params.category ?? ""} onChange={submitOnChange}>
            <option value="">Any</option>
            {filterOptions.categories.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {subcategoryOptions.length > 0 && (
          <div className={styles.field}>
            <label htmlFor="passage-subcategory">Subcategory</label>
            <select id="passage-subcategory" name="subcategory" defaultValue={params.subcategory ?? ""} onChange={submitOnChange}>
              <option value="">Any</option>
              {subcategoryOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className={styles.field}>
          <label htmlFor="passage-rs-quality">Report-side quality</label>
          <select id="passage-rs-quality" name="rsQuality" defaultValue={params.reportSideQuality ?? ""} onChange={submitOnChange}>
            <option value="">Any</option>
            {filterOptions.reportSideQualities.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-ac-quality">Alignment-change quality</label>
          <select id="passage-ac-quality" name="acQuality" defaultValue={params.alignmentChangeQuality ?? ""} onChange={submitOnChange}>
            <option value="">Any</option>
            {filterOptions.alignmentChangeQualities.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-primary">Primary narrative eligible</label>
          <select id="passage-primary" name="primary" defaultValue={triState(params.primaryNarrativeEligible)} onChange={submitOnChange}>
            {TRISTATE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-feature">Feature eligible</label>
          <select id="passage-feature" name="feature" defaultValue={triState(params.featureEligible)} onChange={submitOnChange}>
            {TRISTATE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-irregular-gap">Irregular-gap comparison</label>
          <select id="passage-irregular-gap" name="irregularGap" defaultValue={triState(params.irregularGapComparison)} onChange={submitOnChange}>
            {TRISTATE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-collision">Collision flagged</label>
          <select id="passage-collision" name="collision" defaultValue={triState(params.collisionFlag)} onChange={submitOnChange}>
            {TRISTATE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-split-merge">Split/merge flagged</label>
          <select id="passage-split-merge" name="splitMerge" defaultValue={triState(params.splitMergeFlag)} onChange={submitOnChange}>
            {TRISTATE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label htmlFor="passage-sort">Sort</label>
          <select id="passage-sort" name="sort" defaultValue={params.sort} onChange={submitOnChange}>
            {PASSAGE_SORT_KEYS.map((key: PassageSortKey) => (
              <option key={key} value={key}>
                {PASSAGE_SORT_LABELS[key]}
              </option>
            ))}
          </select>
        </div>

        <div className={`${styles.field} ${styles.advanced}`}>
          <label htmlFor="passage-comparison">Comparison ID (advanced)</label>
          <input
            id="passage-comparison"
            type="text"
            name="comparison"
            defaultValue={params.comparisonId ?? ""}
            placeholder="Paste a comparison ID"
          />
        </div>
      </div>
    </form>
  );
}
