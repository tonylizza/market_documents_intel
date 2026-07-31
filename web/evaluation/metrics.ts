/**
 * Milestone 7B.1 retrieval-evaluation metrics -- pure functions over a
 * ranked id list and a relevance judgment, so they're identical regardless
 * of which mode (keyword/semantic-exact/semantic-hnsw/hybrid-exact/
 * hybrid-hnsw) produced the ranking. Never imports anything from
 * `lib/repositories` or `lib/services` -- keeps this module runnable in a
 * plain unit test with no database.
 */

export type RelevanceGrade = "highly_relevant" | "relevant" | "marginal" | "not_relevant";

const GRADE_WEIGHT: Record<RelevanceGrade, number> = {
  highly_relevant: 3,
  relevant: 2,
  marginal: 1,
  not_relevant: 0,
};

export function recallAtK(ranked: readonly string[], relevant: ReadonlySet<string>, k: number): number {
  if (relevant.size === 0) return 1;
  const top = new Set(ranked.slice(0, k));
  let hits = 0;
  for (const id of relevant) if (top.has(id)) hits += 1;
  return hits / relevant.size;
}

export function precisionAtK(ranked: readonly string[], relevant: ReadonlySet<string>, k: number): number {
  const top = ranked.slice(0, k);
  if (top.length === 0) return 0;
  const hits = top.filter((id) => relevant.has(id)).length;
  return hits / top.length;
}

export function reciprocalRank(ranked: readonly string[], relevant: ReadonlySet<string>): number {
  for (let i = 0; i < ranked.length; i += 1) {
    if (relevant.has(ranked[i])) return 1 / (i + 1);
  }
  return 0;
}

function dcg(gains: readonly number[]): number {
  return gains.reduce((sum, gain, index) => sum + gain / Math.log2(index + 2), 0);
}

/** nDCG@k using graded relevance (0-3). Falls back to binary gains (0/1)
 * when a ranked id has no graded entry but is in the binary relevant set. */
export function ndcgAtK(
  ranked: readonly string[],
  gradedRelevance: ReadonlyMap<string, RelevanceGrade>,
  k: number,
): number {
  const gains = ranked.slice(0, k).map((id) => GRADE_WEIGHT[gradedRelevance.get(id) ?? "not_relevant"]);
  const actual = dcg(gains);
  const ideal = dcg([...gradedRelevance.values()].map((grade) => GRADE_WEIGHT[grade]).sort((a, b) => b - a).slice(0, k));
  return ideal === 0 ? 0 : actual / ideal;
}

export interface CaseMetrics {
  recallAt5: number;
  recallAt10: number;
  precisionAt5: number;
  mrr: number;
  ndcgAt10: number | null;
}

export function computeCaseMetrics(
  ranked: readonly string[],
  relevantIds: readonly string[],
  gradedRelevance?: ReadonlyMap<string, RelevanceGrade>,
): CaseMetrics {
  const relevantSet = new Set(relevantIds);
  return {
    recallAt5: recallAtK(ranked, relevantSet, 5),
    recallAt10: recallAtK(ranked, relevantSet, 10),
    precisionAt5: precisionAtK(ranked, relevantSet, 5),
    mrr: reciprocalRank(ranked, relevantSet),
    ndcgAt10: gradedRelevance && gradedRelevance.size > 0 ? ndcgAtK(ranked, gradedRelevance, 10) : null,
  };
}

export function meanOf(values: readonly number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export interface AggregateMetrics {
  caseCount: number;
  meanRecallAt5: number;
  meanRecallAt10: number;
  meanPrecisionAt5: number;
  meanMrr: number;
  meanNdcgAt10: number | null;
}

// ---------------------------------------------------------------------------
// Milestone 7B.1a: short-passage-inflation and weak-match/no-answer metrics
// ---------------------------------------------------------------------------

/** Fraction of the top-k ranked ids classified as a short fragment
 * (regardless of relevance) -- the headline "did remediation reduce
 * fragment presence" metric. */
export function shortFragmentRateAtK(rankedIsFragment: readonly boolean[], k: number): number {
  const top = rankedIsFragment.slice(0, k);
  if (top.length === 0) return 0;
  return top.filter(Boolean).length / top.length;
}

/** Fraction of the top-k that are BOTH a short fragment AND not actually
 * relevant -- the specific failure mode this milestone targets (a fragment
 * that is also irrelevant "stealing" a top slot from a real answer). A
 * fragment that happens to be genuinely relevant is not counted against
 * this rate. */
export function irrelevantShortFragmentRateAtK(
  ranked: readonly string[],
  isFragment: ReadonlySet<string>,
  relevant: ReadonlySet<string>,
  k: number,
): number {
  const top = ranked.slice(0, k);
  if (top.length === 0) return 0;
  const irrelevantFragments = top.filter((id) => isFragment.has(id) && !relevant.has(id));
  return irrelevantFragments.length / top.length;
}

/** Precision@k counting only hits that are both relevant AND not a short
 * fragment -- distinct from plain `precisionAtK`, which would still credit
 * a relevant-but-fragmentary hit. */
export function substantivePrecisionAtK(
  ranked: readonly string[],
  relevant: ReadonlySet<string>,
  isFragment: ReadonlySet<string>,
  k: number,
): number {
  const top = ranked.slice(0, k);
  if (top.length === 0) return 0;
  const hits = top.filter((id) => relevant.has(id) && !isFragment.has(id));
  return hits.length / top.length;
}

/** Fraction of `similarities` at or above `threshold`. Applied to
 * `no_answer` cases' top-1 similarity, this is the "false strong match
 * rate" (a no-answer query that the weak-match threshold would
 * incorrectly label "strong"). */
export function rateAtOrAboveThreshold(similarities: readonly number[], threshold: number): number {
  if (similarities.length === 0) return 0;
  return similarities.filter((s) => s >= threshold).length / similarities.length;
}

/** Fraction of `similarities` below `threshold`. Applied to answerable
 * cases' top-1 similarity (where a real relevant passage exists), this is
 * the "false weak-match / answerable-query suppression rate" -- a real
 * answer that the threshold would incorrectly label "weak". */
export function rateBelowThreshold(similarities: readonly number[], threshold: number): number {
  if (similarities.length === 0) return 0;
  return similarities.filter((s) => s < threshold).length / similarities.length;
}

export function aggregateMetrics(perCase: readonly CaseMetrics[]): AggregateMetrics {
  const ndcgValues = perCase.map((c) => c.ndcgAt10).filter((v): v is number => v !== null);
  return {
    caseCount: perCase.length,
    meanRecallAt5: meanOf(perCase.map((c) => c.recallAt5)),
    meanRecallAt10: meanOf(perCase.map((c) => c.recallAt10)),
    meanPrecisionAt5: meanOf(perCase.map((c) => c.precisionAt5)),
    meanMrr: meanOf(perCase.map((c) => c.mrr)),
    meanNdcgAt10: ndcgValues.length > 0 ? meanOf(ndcgValues) : null,
  };
}
