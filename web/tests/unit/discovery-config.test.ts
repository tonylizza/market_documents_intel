import { describe, expect, it } from "vitest";
import {
  DISCOVERY_TYPES,
  DISCOVERY_TYPE_CONFIG,
  DEFAULT_RANK_SCOPE,
  RANK_SCOPES,
  isDiscoveryType,
  isRankScope,
  resolveRankScope,
} from "@/lib/config/discovery";

describe("isDiscoveryType", () => {
  it("accepts every one of the 8 known discovery types", () => {
    for (const type of DISCOVERY_TYPES) {
      expect(isDiscoveryType(type)).toBe(true);
    }
  });

  it("rejects an unknown type string", () => {
    expect(isDiscoveryType("largest_made_up_thing")).toBe(false);
    expect(isDiscoveryType(null)).toBe(false);
    expect(isDiscoveryType(undefined)).toBe(false);
  });
});

describe("DISCOVERY_TYPE_CONFIG", () => {
  it("has an entry, with a title and quality dimension, for every discovery type", () => {
    for (const type of DISCOVERY_TYPES) {
      const config = DISCOVERY_TYPE_CONFIG[type];
      expect(config.title.length).toBeGreaterThan(0);
      expect(["report-side", "alignment-change", "disclosure-change"]).toContain(config.qualityDimension);
    }
  });

  it("gates the two feature-quality types on disclosure-change, never a language dimension", () => {
    expect(DISCOVERY_TYPE_CONFIG.largest_overall_change.qualityDimension).toBe("disclosure-change");
    expect(DISCOVERY_TYPE_CONFIG.largest_new_disclosure_share.qualityDimension).toBe("disclosure-change");
  });

  it("gates risk introduction/removal on alignment-change, not report-side", () => {
    expect(DISCOVERY_TYPE_CONFIG.largest_risk_introduction.qualityDimension).toBe("alignment-change");
    expect(DISCOVERY_TYPE_CONFIG.largest_risk_removal.qualityDimension).toBe("alignment-change");
  });
});

describe("isRankScope / resolveRankScope", () => {
  it("accepts all three known scopes", () => {
    for (const scope of RANK_SCOPES) {
      expect(isRankScope(scope)).toBe(true);
    }
  });

  it("rejects an unknown scope", () => {
    expect(isRankScope("global")).toBe(false);
  });

  it("falls back to corpus (the default) for an invalid/missing scope", () => {
    expect(resolveRankScope("not-a-scope")).toBe(DEFAULT_RANK_SCOPE);
    expect(resolveRankScope(null)).toBe(DEFAULT_RANK_SCOPE);
    expect(resolveRankScope(undefined)).toBe("corpus");
  });
});
