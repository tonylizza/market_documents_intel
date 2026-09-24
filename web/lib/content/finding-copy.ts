import { extractFindingPayloadEntry } from "@/lib/schemas/comparison";
import { formatMetricValue } from "@/lib/formatting/numbers";
import { DISCOVERY_TYPES, type DiscoveryType } from "@/lib/config/discovery";
import type { ComparisonSummary, DeterministicFinding } from "@/lib/domain/comparison";

/**
 * Controlled mapping from a published finding/discovery key to UI copy --
 * the *only* place raw finding-key strings are translated to user-facing
 * text. `discovery_type` and `finding_key` share one vocabulary (see
 * `market_documents.publishing.findings.CANDIDATE_KEY_ORDER`), so this one
 * map covers both `DeterministicFinding` headlines and `/discover` ranking
 * titles/descriptions. Exhaustive over `DISCOVERY_TYPES` --
 * `finding-copy.test.ts` asserts every key has an entry.
 */
export interface FindingCopyConfig {
  key: DiscoveryType;
  headline: string;
  description: string;
  unit: "score_0_1" | "rate_per_1000_words" | "share";
}

const FINDING_COPY: Record<DiscoveryType, FindingCopyConfig> = {
  largest_overall_change: {
    key: "largest_overall_change",
    headline: "Overall disclosure change",
    description:
      "Overall disclosure-change magnitude based on passage-alignment change. Not currently published as a Discover ranking: methodology under review.",
    unit: "score_0_1",
  },
  largest_uncertainty_increase: {
    key: "largest_uncertainty_increase",
    headline: "Uncertainty-language increase",
    description:
      "Uncertainty vocabulary increased both in amount and as a share of the narrative, per 1,000 words. This describes wording, not whether the business actually became more uncertain.",
    unit: "rate_per_1000_words",
  },
  largest_negative_tone_shift: {
    key: "largest_negative_tone_shift",
    headline: "Net tone decline",
    description:
      "Positive-word density minus negative-word density fell compared with the prior report, per 1,000 words. A dictionary word-count measure -- see the positive and negative components below; it is not management sentiment or outlook.",
    unit: "rate_per_1000_words",
  },
  largest_risk_introduction: {
    key: "largest_risk_introduction",
    headline: "Risk language in new passages",
    description:
      "Risk-related language in passages classified as new. Not currently published as a Discover ranking: methodology under review.",
    unit: "rate_per_1000_words",
  },
  largest_risk_removal: {
    key: "largest_risk_removal",
    headline: "Risk language in removed passages",
    description:
      "Risk-related language in passages classified as removed. Not currently published as a Discover ranking: methodology under review.",
    unit: "rate_per_1000_words",
  },
  largest_governance_shift: {
    key: "largest_governance_shift",
    headline: "Governance language change",
    description:
      "Governance vocabulary changed both in amount and in how much of the narrative it occupies, per 1,000 words. This does not indicate whether governance quality improved or worsened.",
    unit: "rate_per_1000_words",
  },
  largest_financial_condition_shift: {
    key: "largest_financial_condition_shift",
    headline: "Financial-condition language change",
    description:
      "Financial-condition vocabulary changed both in amount and in how much of the narrative it occupies, per 1,000 words. This describes language, not financial health, performance or risk.",
    unit: "rate_per_1000_words",
  },
  largest_new_disclosure_share: {
    key: "largest_new_disclosure_share",
    headline: "Share of new disclosure",
    description:
      "Share of the report classified as entirely new content. Not currently published as a Discover ranking: methodology under review.",
    unit: "share",
  },
};

const FALLBACK_COPY: Omit<FindingCopyConfig, "key"> = {
  headline: "Notable change detected",
  description: "This comparison was flagged for a notable change that isn't yet described by a known finding key.",
  unit: "rate_per_1000_words",
};

/** Never throws/shows a raw key to the user -- an unrecognized key (e.g. a
 * future publication introducing a new finding type before the frontend is
 * updated) falls back to a safe, generic description instead. */
export function getFindingCopy(key: string): Omit<FindingCopyConfig, "key"> & { key: string } {
  const known = (FINDING_COPY as Record<string, FindingCopyConfig>)[key];
  return known ?? { ...FALLBACK_COPY, key };
}

export function isKnownFindingKey(key: string): key is DiscoveryType {
  return (DISCOVERY_TYPES as readonly string[]).includes(key);
}

/** Builds one `DeterministicFinding` from a comparison's selected finding
 * key + its raw `finding_payload` -- returns `null` for an unfilled slot
 * (`key === null`), never a placeholder finding. */
export function buildDeterministicFinding(
  key: string | null,
  slot: "primary" | "secondary" | "tertiary",
  findingPayload: Record<string, unknown> | null,
): DeterministicFinding | null {
  if (!key) return null;
  const copy = getFindingCopy(key);
  const entry = extractFindingPayloadEntry(findingPayload, key);
  const supportingValue = entry?.value ?? null;
  return {
    key,
    slot,
    headline: copy.headline,
    description: copy.description,
    supportingValue,
    supportingValueDisplay: formatMetricValue(supportingValue, copy.unit),
    supportingUnit: copy.unit,
  };
}

/** Builds up to three `DeterministicFinding`s (primary/secondary/tertiary)
 * from an already-fetched comparison -- a comparison with fewer than three
 * eligible candidates yields fewer findings, never a placeholder slot. */
export function buildFindings(comparison: ComparisonSummary): DeterministicFinding[] {
  const findings = [
    buildDeterministicFinding(comparison.primaryFindingKey, "primary", comparison.findingPayload),
    buildDeterministicFinding(comparison.secondaryFindingKey, "secondary", comparison.findingPayload),
    buildDeterministicFinding(comparison.tertiaryFindingKey, "tertiary", comparison.findingPayload),
  ];
  return findings.filter((finding): finding is DeterministicFinding => finding !== null);
}
