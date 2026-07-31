import type { RetrievalMode } from "@/lib/domain/retrieval";
import type { AggregateMetrics } from "./metrics";

export interface DefaultModeDecisionInput {
  keyword: AggregateMetrics;
  hybrid: AggregateMetrics;
  /** A small tolerance so "effectively tied" doesn't require exact equality
   * of floating-point aggregate scores. */
  tieTolerance?: number;
}

export interface DefaultModeDecision {
  mode: RetrievalMode;
  reason: string;
}

/**
 * Deterministic default-search-mode rule (Milestone 7B.1 acceptance
 * criteria): Hybrid becomes the default only if its nDCG@10 (or MRR, when
 * nDCG@10 data is unavailable) is best-or-tied-best against Keyword AND
 * Keyword's own recall@10 does not regress under Hybrid. Otherwise Keyword
 * remains the default. Semantic-only is never the default (see milestone:
 * "Until then, use Keyword as the default through configuration").
 */
export function decideDefaultSearchMode(input: DefaultModeDecisionInput): DefaultModeDecision {
  const tolerance = input.tieTolerance ?? 0.01;
  const keywordScore = input.keyword.meanNdcgAt10 ?? input.keyword.meanMrr;
  const hybridScore = input.hybrid.meanNdcgAt10 ?? input.hybrid.meanMrr;

  const hybridAtLeastTiedBest = hybridScore >= keywordScore - tolerance;
  const keywordRecallRegresses = input.hybrid.meanRecallAt10 < input.keyword.meanRecallAt10 - tolerance;

  if (hybridAtLeastTiedBest && !keywordRecallRegresses) {
    return {
      mode: "hybrid",
      reason: `hybrid (score=${hybridScore.toFixed(3)}) is tied-or-better than keyword (score=${keywordScore.toFixed(3)}) with no keyword-recall regression`,
    };
  }
  return {
    mode: "keyword",
    reason: !hybridAtLeastTiedBest
      ? `keyword (score=${keywordScore.toFixed(3)}) outperforms hybrid (score=${hybridScore.toFixed(3)})`
      : `hybrid regresses keyword recall@10 (${input.hybrid.meanRecallAt10.toFixed(3)} < ${input.keyword.meanRecallAt10.toFixed(3)})`,
  };
}
