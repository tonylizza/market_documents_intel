import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { getQaConfig, getGateStrategyConfig, DIRECT_RESPONSIVENESS_PRESETS, type DirectResponsivenessPreset } from "@/lib/config/qa-config";

const ENV_KEYS = [
  "QA_CANDIDATE_LIMIT_PER_SOURCE",
  "QA_MAX_EVIDENCE_SET_SIZE",
  "QA_MIN_TOPIC_COVERAGE_RATIO",
  "QA_MIN_RELEVANCE_MARGIN",
  "QA_MAX_REDUNDANCY_RATIO",
  "QA_SECOND_STAGE_RERANKER",
  "QA_DIRECT_RESPONSIVENESS_PRESET",
] as const;

describe("getQaConfig", () => {
  const originalEnv: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const key of ENV_KEYS) {
      originalEnv[key] = process.env[key];
      delete process.env[key];
    }
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      if (originalEnv[key] === undefined) delete process.env[key];
      else process.env[key] = originalEnv[key];
    }
  });

  it("defaults maxEvidenceSetSize to 3 (selected via the real evaluation sweep)", () => {
    expect(getQaConfig().maxEvidenceSetSize).toBe(3);
  });

  it("defaults secondStageReranker to quality_aware", () => {
    expect(getQaConfig().secondStageReranker).toBe("quality_aware");
  });

  it("falls back to the default reranker when the env override is invalid", () => {
    process.env.QA_SECOND_STAGE_RERANKER = "not-a-real-method";
    expect(getQaConfig().secondStageReranker).toBe("quality_aware");
  });

  it("accepts a valid reranker override", () => {
    process.env.QA_SECOND_STAGE_RERANKER = "baseline";
    expect(getQaConfig().secondStageReranker).toBe("baseline");
  });

  it("parses a numeric override for maxEvidenceSetSize and ignores an invalid one", () => {
    process.env.QA_MAX_EVIDENCE_SET_SIZE = "8";
    expect(getQaConfig().maxEvidenceSetSize).toBe(8);
    process.env.QA_MAX_EVIDENCE_SET_SIZE = "not-a-number";
    expect(getQaConfig().maxEvidenceSetSize).toBe(3);
  });

  it("parses a float override for minTopicCoverageRatio", () => {
    process.env.QA_MIN_TOPIC_COVERAGE_RATIO = "0.75";
    expect(getQaConfig().minTopicCoverageRatio).toBe(0.75);
  });
});

describe("Milestone 7B.1c Phase 10 -- direct-responsiveness preset selection", () => {
  it("defaults to the selected provisional preset (query_type_gate_generic_penalty)", () => {
    expect(getQaConfig().directResponsivenessPreset).toBe("query_type_gate_generic_penalty");
  });

  it("accepts a valid preset override and rejects an invalid one", () => {
    process.env.QA_DIRECT_RESPONSIVENESS_PRESET = "full_gate_restatement_safeguards";
    expect(getQaConfig().directResponsivenessPreset).toBe("full_gate_restatement_safeguards");
    process.env.QA_DIRECT_RESPONSIVENESS_PRESET = "not-a-real-preset";
    expect(getQaConfig().directResponsivenessPreset).toBe("query_type_gate_generic_penalty");
  });

  it("resolves every one of the 8 predeclared presets deterministically, each to itself", () => {
    for (const preset of Object.keys(DIRECT_RESPONSIVENESS_PRESETS) as DirectResponsivenessPreset[]) {
      const strategy = getGateStrategyConfig({ ...getQaConfig(), directResponsivenessPreset: preset });
      expect(strategy.preset).toBe(preset);
    }
  });

  it("escalates flags monotonically along the predeclared ladder (each preset a strict extension of the previous)", () => {
    const ladder: DirectResponsivenessPreset[] = [
      "minimal_gate",
      "weighted_gate",
      "weighted_gate_body",
      "query_type_gate",
      "query_type_gate_generic_penalty",
      "full_gate",
      "full_gate_strict_partial",
      "full_gate_restatement_safeguards",
    ];
    expect(DIRECT_RESPONSIVENESS_PRESETS.weighted_gate_body.requireBodyMatch).toBe(true);
    expect(DIRECT_RESPONSIVENESS_PRESETS.weighted_gate.requireBodyMatch).toBe(false);
    expect(DIRECT_RESPONSIVENESS_PRESETS.query_type_gate.applyQueryTypeConditions).toBe(true);
    expect(DIRECT_RESPONSIVENESS_PRESETS.query_type_gate_generic_penalty.applyGenericPenalty).toBe(true);
    expect(DIRECT_RESPONSIVENESS_PRESETS.full_gate.drivesRanking).toBe(true);
    expect(DIRECT_RESPONSIVENESS_PRESETS.full_gate_strict_partial.strictPartialSupport).toBe(true);
    expect(DIRECT_RESPONSIVENESS_PRESETS.full_gate_restatement_safeguards.restatementSafeguards).toBe(true);
    expect(ladder).toHaveLength(8);
  });
});
