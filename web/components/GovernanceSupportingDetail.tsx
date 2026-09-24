import type { GovernanceSubcategoryMover } from "@/lib/services/comparison-service";
import { formatCount, formatMetricValue } from "@/lib/formatting/numbers";
import { formatCategoryLabel } from "@/lib/formatting/labels";
import { DefinitionList } from "./DefinitionList";
import { EmptyState } from "./EmptyState";
import styles from "./GovernanceSupportingDetail.module.css";

export interface GovernanceSupportingDetailProps {
  /** M1-G -- governance-related term density change per 1,000 narrative
   * words. Descriptive context only; never the Discover ranking metric
   * (since Track 7F.9 that's the governance topic change). */
  languageDensityChange: number | null;
  /** M6-G -- topic-mix change, unsigned. */
  topicMixChange: number | null;
  /** Track 7F.7a.1a -- governance's share of classified disclosure, each
   * side (`shareEarlier = hitsEarlier / customTaxonomyHitsEarlier`). */
  shareEarlier: number | null;
  shareLater: number | null;
  /** Track 7F.7a.1a -- raw governance hit counts, each side. */
  hitsEarlier: number | null;
  hitsLater: number | null;
  /** Track 7F.7a.1a -- total custom-taxonomy (risk + financial-condition +
   * governance + strategy) hit counts, each side -- "H" in the M3-G
   * formula (`governanceShare = governanceHits / customTaxonomyHits`). */
  customTaxonomyHitsEarlier: number | null;
  customTaxonomyHitsLater: number | null;
  subcategoryMovers: readonly GovernanceSubcategoryMover[];
}

/**
 * Track 7F.7a.1 items 9/10/11/12, corrected by 7F.7a.1a: M1-G (supporting
 * density context), M6-G (topic-mix change, unsigned, never given a +/-
 * direction), the top governance subcategory movers with hit counts and
 * share contributions, and a factual count/share decomposition of the
 * governance share movement (governance's share of classified disclosure,
 * governance hit counts, and total classified-language hit counts H, each
 * side). The decomposition states observed counts/shares only -- it never
 * classifies the movement as "changed little", "own-volume", or
 * "share-relative" (the `|M1-G| < 1.0` heuristic previously used for that
 * was an undocumented threshold 7F.6 flagged and 7F.7a never validated for
 * this purpose; removed in 7F.7a.1a). Purely supporting detail for a
 * governance finding -- never the Discover ranking metric itself (since
 * Track 7F.9 that's the governance topic change; M3-G is supporting only).
 */
export function GovernanceSupportingDetail({
  languageDensityChange,
  topicMixChange,
  shareEarlier,
  shareLater,
  hitsEarlier,
  hitsLater,
  customTaxonomyHitsEarlier,
  customTaxonomyHitsLater,
  subcategoryMovers,
}: GovernanceSupportingDetailProps) {
  const decomposition = buildShareDecomposition(
    shareEarlier,
    shareLater,
    hitsEarlier,
    hitsLater,
    customTaxonomyHitsEarlier,
    customTaxonomyHitsLater,
  );

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

      {decomposition && <p>{decomposition}</p>}

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
 * Track 7F.7a.1a: factual count/share decomposition of the governance share
 * movement, replacing the removed `|M1-G| < 1.0` heuristic (7F.6 flagged it
 * as undocumented; 7F.7a never validated it as a semantic "changed little"
 * classifier). States the observed governance share/hit counts and total
 * classified-language hit counts H on each side, with no interpretation and
 * no new numeric threshold -- the one narrative exception (per spec) is
 * when governance hits are exactly unchanged, where it is factually
 * accurate (not a classification) to say the share movement came from other
 * classified categories.
 */
function buildShareDecomposition(
  shareEarlier: number | null,
  shareLater: number | null,
  hitsEarlier: number | null,
  hitsLater: number | null,
  taxonomyHitsEarlier: number | null,
  taxonomyHitsLater: number | null,
): string | null {
  if (
    shareEarlier === null ||
    shareLater === null ||
    hitsEarlier === null ||
    hitsLater === null ||
    taxonomyHitsEarlier === null ||
    taxonomyHitsLater === null
  ) {
    return null;
  }
  const earlierSharePct = formatMetricValue(shareEarlier, "share");
  const laterSharePct = formatMetricValue(shareLater, "share");
  const base =
    `Governance language represented ${earlierSharePct} of classified disclosure in the earlier report and ` +
    `${laterSharePct} in the later report. Governance hits changed from ${formatCount(hitsEarlier)} to ` +
    `${formatCount(hitsLater)}, while total classified-language hits changed from ${formatCount(taxonomyHitsEarlier)} ` +
    `to ${formatCount(taxonomyHitsLater)}.`;
  if (hitsEarlier === hitsLater) {
    return `${base} Governance hits did not change, so the share movement came from changes in other classified categories.`;
  }
  return base;
}
