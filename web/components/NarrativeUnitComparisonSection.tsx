import type { NarrativeUnitComparison } from "@/lib/domain/cutover-comparison";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import { formatCount } from "@/lib/formatting/numbers";
import { DefinitionList } from "@/components/DefinitionList";
import styles from "./NarrativeUnitComparisonSection.module.css";

export interface NarrativeUnitComparisonSectionProps {
  narrative: NarrativeUnitComparison;
}

/** User-facing copy for an unresolved/ambiguous/review-required narrative
 * comparison -- deliberately never shows the raw status string
 * (`UNRESOLVED_UPSTREAM` etc.) to ordinary users; that stays available via
 * `data-status` for admin/debug inspection only. */
const UNRESOLVED_COPY: Record<string, { title: string; description: string }> = {
  UNRESOLVED_UPSTREAM: {
    title: "Comparison unavailable for this report pair",
    description: "The source section could not be resolved reliably between these two reports.",
  },
  AMBIGUOUS: {
    title: "Comparison unavailable for this report pair",
    description: "This section matched more than one candidate across the two reports and could not be resolved automatically.",
  },
  REVIEW_REQUIRED: {
    title: "Review required",
    description: "This comparison did not meet the bar for an automated result and needs manual review.",
  },
  NOT_AVAILABLE: {
    title: "Comparison unavailable for this report pair",
    description: "No automated result is available for this section.",
  },
};

function formatSimilarity(value: number | null): string {
  return value === null ? "Not available" : value.toFixed(3);
}

/**
 * Track 7A.3/7A.4: renders a Track 7C.6 semantic-unit narrative comparison.
 * Resolved: lexical metrics, word counts, alignment status. Unresolved:
 * neutral copy in the existing product voice, never the raw enum text.
 */
export function NarrativeUnitComparisonSection({ narrative }: NarrativeUnitComparisonSectionProps) {
  const unitLabel = formatCategoryLabel(narrative.unitKey);

  if (narrative.status !== "RESOLVED") {
    const copy = UNRESOLVED_COPY[narrative.status] ?? UNRESOLVED_COPY.NOT_AVAILABLE;
    return (
      <div className={styles.unresolved} data-status={narrative.status} role="status">
        <p className={styles.unresolvedTitle}>{copy.title}</p>
        <p className={styles.unresolvedDescription}>
          {unitLabel}: {copy.description}
        </p>
      </div>
    );
  }

  const metrics = narrative.lexicalMetrics;

  return (
    <div data-status={narrative.status}>
      <p className={styles.unitLabel}>{unitLabel}</p>
      <DefinitionList
        items={[
          { term: "Earlier word count", description: narrative.earlierWordCount !== null ? formatCount(narrative.earlierWordCount) : "Not available" },
          { term: "Later word count", description: narrative.laterWordCount !== null ? formatCount(narrative.laterWordCount) : "Not available" },
          { term: "Word count change", description: metrics?.wordCountChange !== null && metrics?.wordCountChange !== undefined ? formatCount(metrics.wordCountChange) : "Not available" },
          { term: "TF-IDF cosine similarity", description: formatSimilarity(metrics?.tfidfCosine ?? null) },
          { term: "Unigram Jaccard similarity", description: formatSimilarity(metrics?.unigramJaccard ?? null) },
          { term: "Bigram Jaccard similarity", description: formatSimilarity(metrics?.bigramJaccard ?? null) },
          { term: "Edit similarity", description: formatSimilarity(metrics?.editSimilarity ?? null) },
          { term: "Sequence similarity", description: formatSimilarity(metrics?.sequenceSimilarity ?? null) },
          { term: "Alignment status", description: narrative.alignmentStatus ? formatCategoryLabel(narrative.alignmentStatus) : "Not available" },
          { term: "Alignment confidence", description: narrative.alignmentConfidence ? formatCategoryLabel(narrative.alignmentConfidence) : "Not available" },
        ]}
      />
    </div>
  );
}
