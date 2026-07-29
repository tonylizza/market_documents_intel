import { describe, expect, it } from "vitest";
import { DISCOVERY_TYPES } from "@/lib/config/discovery";
import { buildDeterministicFinding, buildFindings, getFindingCopy, isKnownFindingKey } from "@/lib/content/finding-copy";
import { makeComparisonSummary } from "../fixtures/comparison-fixtures";

describe("getFindingCopy", () => {
  it("has a real, non-fallback entry for every one of the 8 published finding/discovery keys", () => {
    for (const key of DISCOVERY_TYPES) {
      const copy = getFindingCopy(key);
      expect(copy.key).toBe(key);
      expect(copy.headline).not.toBe("Notable change detected");
      expect(copy.headline.length).toBeGreaterThan(0);
      expect(copy.description.length).toBeGreaterThan(0);
    }
  });

  it("falls back to safe generic copy for an unknown key, never showing the raw key as the headline", () => {
    const copy = getFindingCopy("some_future_finding_key");
    expect(copy.key).toBe("some_future_finding_key");
    expect(copy.headline).toBe("Notable change detected");
  });
});

describe("isKnownFindingKey", () => {
  it("matches the discovery-type vocabulary exactly", () => {
    for (const key of DISCOVERY_TYPES) {
      expect(isKnownFindingKey(key)).toBe(true);
    }
    expect(isKnownFindingKey("bogus")).toBe(false);
  });
});

describe("buildDeterministicFinding", () => {
  it("returns null for an unfilled slot (key === null) -- never a placeholder", () => {
    expect(buildDeterministicFinding(null, "secondary", {})).toBeNull();
  });

  it("extracts the supporting value from finding_payload for the given key", () => {
    const payload = { largest_risk_introduction: { value: 2.4, magnitude: 2.4 } };
    const finding = buildDeterministicFinding("largest_risk_introduction", "primary", payload);
    expect(finding).not.toBeNull();
    expect(finding?.supportingValue).toBe(2.4);
    expect(finding?.slot).toBe("primary");
    expect(finding?.headline).toBe("Risk language introduced");
  });

  it("returns a null supporting value (not a thrown error) when the payload doesn't contain the key", () => {
    const finding = buildDeterministicFinding("largest_risk_introduction", "primary", { other_key: { value: 1, magnitude: 1 } });
    expect(finding?.supportingValue).toBeNull();
  });

  it("returns a null supporting value for a malformed payload entry", () => {
    const finding = buildDeterministicFinding("largest_risk_introduction", "primary", {
      largest_risk_introduction: { value: "not-a-number" },
    });
    expect(finding?.supportingValue).toBeNull();
  });
});

describe("buildFindings", () => {
  it("builds up to three findings from primary/secondary/tertiary keys", () => {
    const comparison = makeComparisonSummary({
      primaryFindingKey: "largest_uncertainty_increase",
      secondaryFindingKey: "largest_risk_removal",
      tertiaryFindingKey: "largest_governance_shift",
      findingPayload: {
        largest_uncertainty_increase: { value: 1.5, magnitude: 1.5 },
        largest_risk_removal: { value: 1.1, magnitude: 1.1 },
        largest_governance_shift: { value: 0.9, magnitude: 0.9 },
      },
    });
    const findings = buildFindings(comparison);
    expect(findings).toHaveLength(3);
    expect(findings.map((f) => f.slot)).toEqual(["primary", "secondary", "tertiary"]);
  });

  it("returns fewer than three findings when a comparison has fewer eligible candidates -- never a placeholder", () => {
    const comparison = makeComparisonSummary({
      primaryFindingKey: "largest_uncertainty_increase",
      secondaryFindingKey: null,
      tertiaryFindingKey: null,
    });
    const findings = buildFindings(comparison);
    expect(findings).toHaveLength(1);
  });

  it("returns an empty array when no finding keys are set", () => {
    const comparison = makeComparisonSummary({ primaryFindingKey: null, secondaryFindingKey: null, tertiaryFindingKey: null });
    expect(buildFindings(comparison)).toEqual([]);
  });
});
