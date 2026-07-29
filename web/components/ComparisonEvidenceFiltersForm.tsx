"use client";

import { useRef } from "react";
import type { ComparisonEvidenceFilterOptions, ComparisonEvidenceFilters } from "@/lib/domain/passage";
import styles from "./ComparisonEvidenceFiltersForm.module.css";

export interface ComparisonEvidenceFiltersFormProps {
  comparisonId: string;
  filters: ComparisonEvidenceFilters;
  filterOptions: ComparisonEvidenceFilterOptions;
}

const TRISTATE_OPTIONS = [
  { value: "", label: "Any" },
  { value: "1", label: "Yes" },
  { value: "0", label: "No" },
];

function triState(value: boolean | null): string {
  return value === null ? "" : value ? "1" : "0";
}

/** Evidence-scoped filters -- deliberately excludes company/comparison/side
 * selectors (they have no meaning inside one fixed comparison, per the
 * milestone's "do not duplicate filters" rule). `status` is preserved as a
 * hidden field so changing another filter never resets the active tab. */
export function ComparisonEvidenceFiltersForm({ comparisonId, filters, filterOptions }: ComparisonEvidenceFiltersFormProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const subcategoryOptions = filters.category ? (filterOptions.subcategoriesByCategory[filters.category] ?? []) : [];

  function submitOnChange() {
    formRef.current?.requestSubmit();
  }

  return (
    <form
      ref={formRef}
      method="get"
      action={`/comparisons/${comparisonId}/evidence`}
      aria-label="Evidence filters"
      className={styles.form}
    >
      {filters.status !== "ALL" && <input type="hidden" name="status" value={filters.status} />}

      <div className={styles.field}>
        <label htmlFor="evidence-confidence">Confidence</label>
        <select id="evidence-confidence" name="confidence" defaultValue={filters.confidence ?? ""} onChange={submitOnChange}>
          <option value="">Any</option>
          {filterOptions.confidenceLevels.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label htmlFor="evidence-category">Language category</label>
        <select id="evidence-category" name="category" defaultValue={filters.category ?? ""} onChange={submitOnChange}>
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
          <label htmlFor="evidence-subcategory">Risk / taxonomy subcategory</label>
          <select id="evidence-subcategory" name="subcategory" defaultValue={filters.subcategory ?? ""} onChange={submitOnChange}>
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
        <label htmlFor="evidence-heading">Has heading</label>
        <select id="evidence-heading" name="heading" defaultValue={triState(filters.hasHeading)} onChange={submitOnChange}>
          {TRISTATE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label htmlFor="evidence-collision">Collision flagged</label>
        <select id="evidence-collision" name="collision" defaultValue={triState(filters.collisionFlag)} onChange={submitOnChange}>
          {TRISTATE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label htmlFor="evidence-split-merge">Split/merge flagged</label>
        <select id="evidence-split-merge" name="splitMerge" defaultValue={triState(filters.splitMergeFlag)} onChange={submitOnChange}>
          {TRISTATE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.field}>
        <label htmlFor="evidence-page-start">Page from</label>
        <input
          id="evidence-page-start"
          type="number"
          min={1}
          name="pageStart"
          defaultValue={filters.pageStart ?? ""}
          onChange={submitOnChange}
        />
      </div>
      <div className={styles.field}>
        <label htmlFor="evidence-page-end">Page to</label>
        <input id="evidence-page-end" type="number" min={1} name="pageEnd" defaultValue={filters.pageEnd ?? ""} onChange={submitOnChange} />
      </div>

      <button type="submit" className={styles.submit}>
        Apply filters
      </button>
    </form>
  );
}
