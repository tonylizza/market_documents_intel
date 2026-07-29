import type { QualityDimension } from "@/lib/domain/quality";

/**
 * The complete, exhaustive `discovery_type`/`finding_key` vocabulary (see
 * `market_documents.publishing.findings.CANDIDATE_KEY_ORDER` -- discovery
 * types and finding keys share one vocabulary on the Python side). Two
 * entries (`largest_overall_change`, `largest_new_disclosure_share`) are
 * feature-quality-gated and currently empty in the published corpus because
 * `disclosure_change_quality` is `NEEDS_REVIEW` corpus-wide -- they remain
 * listed here (so a future publication with primary-eligible feature scores
 * renders correctly without a code change) but must never be shown as an
 * empty ranking tab; see `discovery-service.ts`.
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

export interface DiscoveryTypeConfig {
  type: DiscoveryType;
  title: string;
  shortLabel: string;
  /** Which quality dimension gates this ranking's eligibility -- drives the
   * type-specific "minimum quality" filter vocabulary. Never a combined/
   * generic quality filter across dimensions. */
  qualityDimension: QualityDimension;
  description: string;
}

export const DISCOVERY_TYPE_CONFIG: Record<DiscoveryType, DiscoveryTypeConfig> = {
  largest_overall_change: {
    type: "largest_overall_change",
    title: "Largest overall disclosure change",
    shortLabel: "Overall change",
    qualityDimension: "disclosure-change",
    description: "Comparisons with the largest overall disclosure-change magnitude, gated on disclosure-change quality.",
  },
  largest_uncertainty_increase: {
    type: "largest_uncertainty_increase",
    title: "Largest uncertainty increase",
    shortLabel: "Uncertainty increase",
    qualityDimension: "report-side",
    description: "Comparisons where uncertainty-related language increased the most, gated on report-side quality.",
  },
  largest_negative_tone_shift: {
    type: "largest_negative_tone_shift",
    title: "Largest negative-tone shift",
    shortLabel: "Negative tone shift",
    qualityDimension: "report-side",
    description: "Comparisons where overall tone shifted most negatively, gated on report-side quality.",
  },
  largest_risk_introduction: {
    type: "largest_risk_introduction",
    title: "Largest risk-language introduction",
    shortLabel: "Risk introduced",
    qualityDimension: "alignment-change",
    description: "Comparisons with the most newly introduced risk-related language, gated on alignment-change quality.",
  },
  largest_risk_removal: {
    type: "largest_risk_removal",
    title: "Largest risk-language removal",
    shortLabel: "Risk removed",
    qualityDimension: "alignment-change",
    description: "Comparisons with the most removed risk-related language, gated on alignment-change quality.",
  },
  largest_governance_shift: {
    type: "largest_governance_shift",
    title: "Largest governance-language shift",
    shortLabel: "Governance shift",
    qualityDimension: "report-side",
    description: "Comparisons with the largest change in governance-related language, gated on report-side quality.",
  },
  largest_financial_condition_shift: {
    type: "largest_financial_condition_shift",
    title: "Largest financial-condition shift",
    shortLabel: "Financial-condition shift",
    qualityDimension: "report-side",
    description: "Comparisons with the largest change in financial-condition language, gated on report-side quality.",
  },
  largest_new_disclosure_share: {
    type: "largest_new_disclosure_share",
    title: "Largest new-disclosure share",
    shortLabel: "New disclosure share",
    qualityDimension: "disclosure-change",
    description: "Comparisons with the largest share of entirely new disclosure content, gated on disclosure-change quality.",
  },
};

export const RANK_SCOPES = ["corpus", "company_history", "latest_comparisons"] as const;
export type RankScope = (typeof RANK_SCOPES)[number];

export function isRankScope(value: string | null | undefined): value is RankScope {
  return typeof value === "string" && (RANK_SCOPES as readonly string[]).includes(value);
}

export const DEFAULT_RANK_SCOPE: RankScope = "corpus";

export function resolveRankScope(value: string | null | undefined): RankScope {
  return isRankScope(value) ? value : DEFAULT_RANK_SCOPE;
}
