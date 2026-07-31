import "server-only";
import type { QaRerankerMethod } from "@/lib/domain/qa-evidence";
import { DEFAULT_DIRECT_RESPONSIVENESS_FLOOR, type DirectResponsivenessStrategyConfig } from "@/lib/services/qa/direct-responsiveness";

/**
 * Milestone 7B.1b: Q&A evidence-selection tuning knobs. Mirrors
 * `lib/config/retrieval-config.ts`'s pattern exactly -- server-only
 * configuration, never an ordinary user control, read once per process from
 * environment variables with defaults chosen from real-corpus evaluation
 * (see the Milestone 7B.1b final report for the `maxEvidenceSetSize` sweep
 * over 3/5/8 and the reranker-selection experiment).
 */

function envInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function envFloat(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function envQaReranker(name: string, fallback: QaRerankerMethod): QaRerankerMethod {
  const raw = process.env[name];
  if (raw === "baseline" || raw === "concept_coverage" || raw === "quality_aware") return raw;
  return fallback;
}

export interface QaConfig {
  /** Maximum number of candidates fetched per source (keyword/semantic) --
   * bounded so the reranker/evidence-set builder never operates on more than
   * a small, deliberately-sized candidate pool (see milestone: "do not send
   * all 21,962 vectors ... into application memory"). */
  candidateLimitPerSource: number;
  /** Maximum size of a constructed evidence set. Evaluated at 3/5/8 against
   * the real 74-case evaluation dataset (predeclared rule: smallest size
   * that does not reduce answerable-question coverage by more than 5
   * percentage points versus the largest size tested). Size 3 (coverage
   * 0.333, redundancy 0.297) qualified over size 5 (coverage 0.352,
   * redundancy 0.522) and size 8 (coverage 0.352, redundancy 0.543) --
   * larger sizes barely improved coverage while nearly doubling
   * redundancy. See the Milestone 7B.1b final report. */
  maxEvidenceSetSize: number;
  /** Below this fraction of an evidence set's required facets being covered,
   * the gate treats topic coverage as insufficient
   * (`INSUFFICIENT_TOPIC_COVERAGE`). */
  minTopicCoverageRatio: number;
  /** Minimum acceptable margin between the top selected candidate's adjusted
   * score and the corpus's existing weak-match floor
   * (`minimumSemanticSimilarity`) -- reused, not a second invented
   * threshold. Below this, the gate raises `LOW_RELEVANCE_MARGIN`. */
  minRelevanceMargin: number;
  /** Above this fraction of near-duplicate/no-new-coverage candidates
   * encountered during evidence-set construction, the gate raises
   * `EVIDENCE_REDUNDANT`. Recalibrated from the real observed distribution
   * of `redundancyRatio` across the 45 genuinely `SUPPORTED`-expected
   * evaluation cases (median 0.80, p75 0.85, p90 0.85) -- with a small
   * facet space (4 disclosure categories + subcategories + report side)
   * and a bounded examination window, even a correctly-answered single-
   * topic question naturally exhausts its facets within the first couple
   * of picks, so most subsequent (still genuinely on-topic) candidates
   * register as "no new facet" by construction, not because the selected
   * evidence itself repeats. The previous default (0.5) was an unvalidated
   * guess and made `EVIDENCE_REDUNDANT` the dominant misclassification
   * reason for correctly-supported questions. See the Milestone 7B.1b
   * final report. */
  maxRedundancyRatio: number;
  /** Which second-stage reranker ships as the default -- selected via the
   * same predeclared-gate evaluation discipline as Milestone 7B.1a's
   * `quality_multiplier` selection. Real evaluation found `concept_coverage`
   * and `quality_aware` genuinely tied (identical answerable-question
   * coverage to full precision, 0.35185185185185186, on the 74-case
   * dataset) -- kept `quality_aware` since it additionally carries the
   * numeric-fragment/heading-fragment quality awareness this milestone's
   * Phase E work added, which `concept_coverage` lacks and which this
   * particular dataset's ties don't happen to exercise. Same tie-break
   * principle as Milestone 7B.1a (prefer the more complete, already-
   * integrated strategy on a genuine statistical tie). */
  secondStageReranker: QaRerankerMethod;
  /** Milestone 7B.1c Phase 10 -- which named direct-responsiveness gate
   * strategy ships. Default is the ladder's final rung
   * (`full_gate_restatement_safeguards`); see the final report for the
   * bounded-grid evaluation this was selected from. */
  directResponsivenessPreset: DirectResponsivenessPreset;
}

/**
 * Milestone 7B.1c Phase 10: 8 predeclared, named direct-responsiveness
 * gate strategies, evaluated as a bounded grid over the real 74-case
 * dataset (`evaluation/run-qa-gate-experiment.ts`) rather than as
 * independently hand-written code paths -- each is a fixed composition of
 * the same underlying boolean flags, so the grid is genuinely bounded and
 * auditable (no hidden per-preset logic). Ladder, each step adding exactly
 * one capability from the milestone's declared Phase 4 evaluation list:
 * 1. `minimal_gate` -- binary required-family gate only.
 * 2. `weighted_gate` -- weighted required-coverage threshold.
 * 3. `weighted_gate_body` -- + body-match requirement.
 * 4. `query_type_gate` -- + query-type-specific conditions.
 * 5. `query_type_gate_generic_penalty` -- + generic-language penalty.
 * 6. `full_gate` -- all of the above + directional/quantitative/causal
 *    constraints (folded into "query-type conditions" above) + the score
 *    also drives reranking, not just eligibility.
 * 7. `full_gate_strict_partial` -- + Phase 6's strict PARTIALLY_SUPPORTED.
 * 8. `full_gate_restatement_safeguards` -- + Phase 7/8's restatement and
 *    comparison/chronology safeguards.
 */
export type DirectResponsivenessPreset =
  | "minimal_gate"
  | "weighted_gate"
  | "weighted_gate_body"
  | "query_type_gate"
  | "query_type_gate_generic_penalty"
  | "full_gate"
  | "full_gate_strict_partial"
  | "full_gate_restatement_safeguards";

export interface GateStrategyConfig extends DirectResponsivenessStrategyConfig {
  preset: DirectResponsivenessPreset;
  /** Phase 4 strategy #8 vs #7 -- whether `directResponsivenessScore` also
   * determines candidate ranking (`true`) or is used purely for
   * eligibility while the existing reranker's order stands (`false`). */
  drivesRanking: boolean;
  /** Phase 6 -- strict, separable-elements-only `PARTIALLY_SUPPORTED`. */
  strictPartialSupport: boolean;
  /** Phase 7/8 -- restatement chronology + comparison/chronology
   * safeguards in the groundedness gate. */
  restatementSafeguards: boolean;
}

const MINIMAL_FLOOR = 0.01;

export const DIRECT_RESPONSIVENESS_PRESETS: Record<DirectResponsivenessPreset, GateStrategyConfig> = {
  minimal_gate: {
    preset: "minimal_gate",
    requireBodyMatch: false,
    applyGenericPenalty: false,
    applyQueryTypeConditions: false,
    directResponsivenessFloor: MINIMAL_FLOOR,
    drivesRanking: false,
    strictPartialSupport: false,
    restatementSafeguards: false,
  },
  weighted_gate: {
    preset: "weighted_gate",
    requireBodyMatch: false,
    applyGenericPenalty: false,
    applyQueryTypeConditions: false,
    directResponsivenessFloor: DEFAULT_DIRECT_RESPONSIVENESS_FLOOR,
    drivesRanking: false,
    strictPartialSupport: false,
    restatementSafeguards: false,
  },
  weighted_gate_body: {
    preset: "weighted_gate_body",
    requireBodyMatch: true,
    applyGenericPenalty: false,
    applyQueryTypeConditions: false,
    directResponsivenessFloor: DEFAULT_DIRECT_RESPONSIVENESS_FLOOR,
    drivesRanking: false,
    strictPartialSupport: false,
    restatementSafeguards: false,
  },
  query_type_gate: {
    preset: "query_type_gate",
    requireBodyMatch: true,
    applyGenericPenalty: false,
    applyQueryTypeConditions: true,
    directResponsivenessFloor: DEFAULT_DIRECT_RESPONSIVENESS_FLOOR,
    drivesRanking: false,
    strictPartialSupport: false,
    restatementSafeguards: false,
  },
  query_type_gate_generic_penalty: {
    preset: "query_type_gate_generic_penalty",
    requireBodyMatch: true,
    applyGenericPenalty: true,
    applyQueryTypeConditions: true,
    directResponsivenessFloor: DEFAULT_DIRECT_RESPONSIVENESS_FLOOR,
    drivesRanking: false,
    strictPartialSupport: false,
    restatementSafeguards: false,
  },
  full_gate: {
    preset: "full_gate",
    requireBodyMatch: true,
    applyGenericPenalty: true,
    applyQueryTypeConditions: true,
    directResponsivenessFloor: DEFAULT_DIRECT_RESPONSIVENESS_FLOOR,
    drivesRanking: true,
    strictPartialSupport: false,
    restatementSafeguards: false,
  },
  full_gate_strict_partial: {
    preset: "full_gate_strict_partial",
    requireBodyMatch: true,
    applyGenericPenalty: true,
    applyQueryTypeConditions: true,
    directResponsivenessFloor: DEFAULT_DIRECT_RESPONSIVENESS_FLOOR,
    drivesRanking: true,
    strictPartialSupport: true,
    restatementSafeguards: false,
  },
  full_gate_restatement_safeguards: {
    preset: "full_gate_restatement_safeguards",
    requireBodyMatch: true,
    applyGenericPenalty: true,
    applyQueryTypeConditions: true,
    directResponsivenessFloor: DEFAULT_DIRECT_RESPONSIVENESS_FLOOR,
    drivesRanking: true,
    strictPartialSupport: true,
    restatementSafeguards: true,
  },
};

function envDirectResponsivenessPreset(name: string, fallback: DirectResponsivenessPreset): DirectResponsivenessPreset {
  const raw = process.env[name];
  return raw && raw in DIRECT_RESPONSIVENESS_PRESETS ? (raw as DirectResponsivenessPreset) : fallback;
}

export function getQaConfig(): QaConfig {
  return {
    candidateLimitPerSource: envInt("QA_CANDIDATE_LIMIT_PER_SOURCE", 40),
    maxEvidenceSetSize: envInt("QA_MAX_EVIDENCE_SET_SIZE", 3),
    minTopicCoverageRatio: envFloat("QA_MIN_TOPIC_COVERAGE_RATIO", 0.5),
    minRelevanceMargin: envFloat("QA_MIN_RELEVANCE_MARGIN", 0.02),
    maxRedundancyRatio: envFloat("QA_MAX_REDUNDANCY_RATIO", 0.9),
    secondStageReranker: envQaReranker("QA_SECOND_STAGE_RERANKER", "quality_aware"),
    // Milestone 7B.1c Phase 10: none of the 8 predeclared presets cleared
    // every READY-FOR-7B.2 threshold on the real 74-case dataset (see the
    // final report and `evaluation/results/qa_gate_strategy_experiment.csv`).
    // `query_type_gate_generic_penalty` is the best available balance --
    // the only preset combining a passing no-answer false-support rate
    // (<=10%) with a passing correct-abstention rate (>=85%) -- but ships
    // provisionally, not as a claim of readiness.
    directResponsivenessPreset: envDirectResponsivenessPreset("QA_DIRECT_RESPONSIVENESS_PRESET", "query_type_gate_generic_penalty"),
  };
}

export function getGateStrategyConfig(config: QaConfig): GateStrategyConfig {
  return DIRECT_RESPONSIVENESS_PRESETS[config.directResponsivenessPreset];
}
