import type { GovernanceSubcategoryMover } from "@/lib/services/comparison-service";
import { formatMetricValue } from "@/lib/formatting/numbers";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import { DefinitionList } from "./DefinitionList";
import { EmptyState } from "./EmptyState";
import styles from "./GovernanceSupportingDetail.module.css";

export interface GovernanceSupportingDetailProps {
  /** M1-G -- governance-related term density change per 1,000 narrative
   * words. Descriptive context only; never the Discover ranking metric
   * (that's M3-G, `governanceShareChange`, shown via the finding itself). */
  languageDensityChange: number | null;
  /** M3-G -- the Discover ranking/materiality metric, shown here again so
   * the share-relative interpretation below can reference it directly. */
  shareChange: number | null;
  /** M6-G -- topic-mix change, unsigned. */
  topicMixChange: number | null;
  subcategoryMovers: readonly GovernanceSubcategoryMover[];
}

/**
 * Track 7F.7a.1 items 9/10/11/12: M1-G (supporting density context), M6-G
 * (topic-mix change, unsigned, never given a +/- direction), the top
 * governance subcategory movers with hit counts and share contributions,
 * and a share-relative interpretation branch distinguishing governance's
 * own-volume movement (M1-G moved in the same direction and magnitude as
 * M3-G would suggest) from share-relative movement (M1-G is flat/small
 * while M3-G moved because other custom-taxonomy categories changed more).
 * Purely supporting detail for a governance finding -- never the Discover
 * ranking metric itself (that's M3-G, shown via the finding itself).
 */
export function GovernanceSupportingDetail({
  languageDensityChange,
  shareChange,
  topicMixChange,
  subcategoryMovers,
}: GovernanceSupportingDetailProps) {
  const interpretation = buildShareRelativeInterpretation(languageDensityChange, shareChange);

  return (
    <div className={styles.wrapper}>
      <DefinitionList
        items={[
          {
            term: "Governance language density change (M1-G)",
            description:
              (formatMetricValue(languageDensityChange, "rate_per_1000_words") ?? "Not available") +
              " -- change in governance-related term density per 1,000 narrative words. Descriptive context only; not the ranking metric.",
          },
          {
            term: "Topic-mix change (M6-G)",
            description:
              (formatMetricValue(topicMixChange, "distance_0_1") ?? "Not available") +
              " -- how much the mix of board/audit/remuneration/etc. topics within governance language changed. Supporting detail only; no positive/negative direction.",
          },
        ]}
      />

      {interpretation && <p className={styles.caution}>{interpretation}</p>}

      {subcategoryMovers.length === 0 ? (
        <EmptyState
          title="No subcategory detail available"
          description="No governance subcategory hits were recorded for this comparison."
        />
      ) : (
        <table className={styles.table}>
          <caption className="visually-hidden">Dominant governance subcategory movers</caption>
          <thead>
            <tr>
              <th scope="col">Subcategory</th>
              <th scope="col">Earlier hits</th>
              <th scope="col">Later hits</th>
              <th scope="col">Change</th>
              <th scope="col">Earlier share contribution</th>
              <th scope="col">Later share contribution</th>
            </tr>
          </thead>
          <tbody>
            {subcategoryMovers.map((mover) => (
              <tr key={mover.id}>
                <td>
                  {mover.subcategory ? formatCategoryLabel(mover.subcategory) : "—"}
                  {mover.lowVolume && (
                    <span className={styles.caution}> (low corpus-wide volume -- interpret with caution)</span>
                  )}
                </td>
                <td>{mover.earlierCount}</td>
                <td>{mover.laterCount}</td>
                <td>{`${mover.change >= 0 ? "+" : ""}${mover.change}`}</td>
                <td>{formatMetricValue(mover.earlierShareContribution, "share") ?? "—"}</td>
                <td>{formatMetricValue(mover.laterShareContribution, "share") ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/**
 * Track 7F.7a.1 item 9 (mandatory): distinguishes governance-own-volume
 * movement from share-relative movement caused primarily by changes in
 * other custom-taxonomy categories. Heuristic (not a new severity system):
 * if M3-G is materially large while M1-G is small/flat, the share moved
 * mostly because other categories changed, not because governance language
 * itself changed much -- surfaced as descriptive text, never a claim of
 * causality beyond the observed counts.
 */
function buildShareRelativeInterpretation(languageDensityChange: number | null, shareChange: number | null): string | null {
  if (shareChange === null) return null;
  const shareMagnitude = Math.abs(shareChange);
  if (shareMagnitude < 0.05) return null; // below materiality -- no interpretation needed here
  const densityMagnitude = languageDensityChange === null ? null : Math.abs(languageDensityChange);
  const isShareRelative = densityMagnitude === null || densityMagnitude < 1.0;
  if (isShareRelative) {
    return "Governance language itself changed little, but its share of classified disclosure moved because other disclosure topics grew or shrank more.";
  }
  return "Governance language's own volume moved in a direction consistent with its share change.";
}
