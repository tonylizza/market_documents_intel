import type { QualityDimension } from "@/lib/domain/quality";

/**
 * The complete, exhaustive `discovery_type`/`finding_key` vocabulary (see
 * `market_documents.publishing.findings.CANDIDATE_KEY_ORDER` -- discovery
 * types and finding keys share one vocabulary on the Python side). Keys are
 * stable identifiers, not product copy (e.g. `largest_negative_tone_shift`
 * is presented as "Net tone decline" since Track 7F.9).
 */
export const DISCOVERY_TYPES = [
  "largest_overall_change",
  "largest_uncertainty_increase",
  "largest_negative_tone_shift",
  "largest_risk_introduction",
  "largest_risk_removal",
  "largest_governance_shift",
  "largest_financial_condition_shift",
  "largest_new_disclosure_share",
] as const;

export type DiscoveryType = (typeof DISCOVERY_TYPES)[number];

export function isDiscoveryType(value: string | null | undefined): value is DiscoveryType {
  return typeof value === "string" && (DISCOVERY_TYPES as readonly string[]).includes(value);
}

/** Track 7F.9 -- `under_review` mirrors `findings.DISABLED_CANDIDATE_KEYS`:
 * the methodology is not currently published, so the ranking is shown as
 * "not currently published" rather than as an empty result (an empty result
 * would wrongly suggest no change occurred). */
export type DiscoveryPublicationStatus = "published" | "under_review";

export interface DiscoveryTypeConfig {
  type: DiscoveryType;
  title: string;
  shortLabel: string;
  /** Which quality dimension gates this ranking's eligibility -- drives the
   * type-specific "minimum quality" filter vocabulary. Never a combined/
   * generic quality filter across dimensions. */
  qualityDimension: QualityDimension;
  description: string;
  publicationStatus: DiscoveryPublicationStatus;
  /** Plain-language reason, only for `under_review` types. */
  underReviewReason?: string;
}

export const DISCOVERY_TYPE_CONFIG: Record<DiscoveryType, DiscoveryTypeConfig> = {
  largest_financial_condition_shift: {
    type: "largest_financial_condition_shift",
    title: "Financial-condition language change",
    shortLabel: "Financial-condition language",
    qualityDimension: "report-side",
    description:
      "Comparisons where financial-condition vocabulary (liquidity, debt, dividends, impairment and similar) changed both in amount and in how much of the narrative it occupies, per 1,000 words. Counted only when both moved the same way. Describes language, not financial health, performance or risk. Gated on report-side quality.",
    publicationStatus: "published",
  },
  largest_governance_shift: {
    type: "largest_governance_shift",
    title: "Governance language change",
    shortLabel: "Governance language",
    qualityDimension: "report-side",
    description:
      "Comparisons where governance vocabulary (board, audit, remuneration, compliance and similar) changed both in amount and in how much of the narrative it occupies, per 1,000 words. Counted only when both moved the same way. Does not indicate whether governance quality improved or worsened. Gated on report-side quality.",
    publicationStatus: "published",
  },
  largest_uncertainty_increase: {
    type: "largest_uncertainty_increase",
    title: "Uncertainty-language increase",
    shortLabel: "Uncertainty language",
    qualityDimension: "report-side",
    description:
      "Comparisons where Loughran-McDonald uncertainty vocabulary increased both in amount and as a share of the narrative, per 1,000 words. Describes wording, not whether the business actually became more uncertain. Gated on report-side quality.",
    publicationStatus: "published",
  },
  largest_negative_tone_shift: {
    type: "largest_negative_tone_shift",
    title: "Net tone decline",
    shortLabel: "Net tone decline",
    qualityDimension: "report-side",
    description:
      "Comparisons where Loughran-McDonald positive-word density minus negative-word density fell the most, per 1,000 words -- from fewer positive words, more negative words, or both. A dictionary word-count measure, not management sentiment or outlook. Gated on report-side quality.",
    publicationStatus: "published",
  },
  largest_risk_introduction: {
    type: "largest_risk_introduction",
    title: "Risk-language introduction",
    shortLabel: "Risk introduced",
    qualityDimension: "alignment-change",
    description: "Risk-related language in passages classified as new since the prior report.",
    publicationStatus: "under_review",
    underReviewReason:
      "Passages that moved or were reorganized can be misclassified as new, so this ranking is not currently published.",
  },
  largest_risk_removal: {
    type: "largest_risk_removal",
    title: "Risk-language removal",
    shortLabel: "Risk removed",
    qualityDimension: "alignment-change",
    description: "Risk-related language in passages classified as removed since the prior report.",
    publicationStatus: "under_review",
    underReviewReason:
      "Passages that moved or were reorganized can be misclassified as removed, so this ranking is not currently published.",
  },
  largest_overall_change: {
    type: "largest_overall_change",
    title: "Overall disclosure change",
    shortLabel: "Overall change",
    qualityDimension: "disclosure-change",
    description: "Comparisons with the largest overall disclosure-change magnitude.",
    publicationStatus: "under_review",
    underReviewReason:
      "The passage-alignment quality this score depends on is being recalibrated, so this ranking is not currently published.",
  },
  largest_new_disclosure_share: {
    type: "largest_new_disclosure_share",
    title: "New-disclosure share",
    shortLabel: "New disclosure share",
    qualityDimension: "disclosure-change",
    description: "Comparisons with the largest share of content classified as entirely new.",
    publicationStatus: "under_review",
    underReviewReason:
      "This ranking depends on the same passage-alignment quality as the overall disclosure-change score, so it is not currently published.",
  },
};

/** Published types in display order (Discover tab order). */
export const PUBLISHED_DISCOVERY_TYPES: readonly DiscoveryType[] = (
  Object.values(DISCOVERY_TYPE_CONFIG) as DiscoveryTypeConfig[]
)
  .filter((c) => c.publicationStatus === "published")
  .map((c) => c.type);

/** Types whose methodology is not currently published / under review. */
export const UNDER_REVIEW_DISCOVERY_TYPES: readonly DiscoveryType[] = (
  Object.values(DISCOVERY_TYPE_CONFIG) as DiscoveryTypeConfig[]
)
  .filter((c) => c.publicationStatus === "under_review")
  .map((c) => c.type);

export const RANK_SCOPES = ["corpus", "company_history", "latest_comparisons"] as const;
export type RankScope = (typeof RANK_SCOPES)[number];

export function isRankScope(value: string | null | undefined): value is RankScope {
  return typeof value === "string" && (RANK_SCOPES as readonly string[]).includes(value);
}

export const DEFAULT_RANK_SCOPE: RankScope = "corpus";

export function resolveRankScope(value: string | null | undefined): RankScope {
  return isRankScope(value) ? value : DEFAULT_RANK_SCOPE;
}
