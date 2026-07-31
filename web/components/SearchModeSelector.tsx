import type { RetrievalMode } from "@/lib/domain/retrieval";
import styles from "./SearchModeSelector.module.css";

export interface SearchModeSelectorProps {
  mode: RetrievalMode;
  onChange?: () => void;
}

const MODE_DESCRIPTIONS: Record<RetrievalMode, { label: string; description: string }> = {
  keyword: {
    label: "Keyword",
    description: "Finds passages containing related search words and phrases.",
  },
  semantic: {
    label: "Semantic",
    description: "Finds passages with similar meaning even when the wording differs.",
  },
  hybrid: {
    label: "Hybrid",
    description: "Combines keyword and meaning-based retrieval.",
  },
};

const MODE_ORDER: readonly RetrievalMode[] = ["keyword", "semantic", "hybrid"];

/**
 * Radio-group search-mode control -- a real `<input type="radio" name="mode">`
 * so it participates in the same progressive-enhancement `<form
 * method="get">` as the rest of `/passages`'s filters (works without
 * JavaScript; auto-submits via `onChange` as an enhancement). Never a
 * hidden/technical control -- every option has a plain-language description,
 * per the milestone's "explain each mode in plain language" requirement.
 */
export function SearchModeSelector({ mode, onChange }: SearchModeSelectorProps) {
  return (
    <fieldset className={styles.fieldset}>
      <legend className={styles.legend}>Search mode</legend>
      <div className={styles.options} role="radiogroup" aria-label="Search mode">
        {MODE_ORDER.map((value) => {
          const { label, description } = MODE_DESCRIPTIONS[value];
          const inputId = `search-mode-${value}`;
          return (
            <label key={value} htmlFor={inputId} className={styles.option} data-selected={mode === value}>
              <input
                id={inputId}
                type="radio"
                name="mode"
                value={value}
                defaultChecked={mode === value}
                onChange={onChange}
                className={styles.radio}
              />
              <span className={styles.optionText}>
                <span className={styles.optionLabel}>{label}</span>
                <span className={styles.optionDescription}>{description}</span>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
