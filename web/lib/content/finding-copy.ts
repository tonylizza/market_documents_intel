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
    headline: "Largest overall disclosure change",
    description:
      "This comparison has the largest overall disclosure-change magnitude currently published, based on lexical and structural passage-alignment change.",
    unit: "score_0_1",
  },
  largest_uncertainty_increase: {
    key: "largest_uncertainty_increase",
    headline: "Uncertainty language increased",
    description: "Uncertainty-related language increased notably compared with the prior report.",
    unit: "rate_per_1000_words",
  },
  largest_negative_tone_shift: {
    key: "largest_negative_tone_shift",
    headline: "Tone shifted more negative",
    description: "Overall language tone shifted notably more negative compared with the prior report.",
    unit: "rate_per_1000_words",
  },
  largest_risk_introduction: {
    key: "largest_risk_introduction",
    headline: "Risk language introduced",
    description:
      "New risk-related language was introduced in passages that are new or substantially changed since the prior report.",
    unit: "rate_per_1000_words",
  },
  largest_risk_removal: {
    key: "largest_risk_removal",
    headline: "Risk language removed",
    description: "Previously present risk-related language was removed from passages changed since the prior report.",
    unit: "rate_per_1000_words",
  },
  largest_governance_shift: {
    key: "largest_governance_shift",
    headline: "Governance language changed",
    description: "Governance-related language changed notably compared with the prior report.",
    unit: "rate_per_1000_words",
  },
  largest_financial_condition_shift: {
    key: "largest_financial_condition_shift",
    headline: "Financial-condition language changed",
    description: "Language describing financial condition changed notably compared with the prior report.",
    unit: "rate_per_1000_words",
  },
  largest_new_disclosure_share: {
    key: "largest_new_disclosure_share",
    headline: "Large share of new disclosure",
    description: "A notably large share of this report's content is entirely new disclosure not present in the prior report.",
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
